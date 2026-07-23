import json
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import Config
from services.media_attention_alert_store import MediaAttentionAlertStore
from services.media_attention_monitor_service import MediaAttentionMonitorService
from services.media_attention_service import MediaAttentionService
from services.media_attention_state_store import MediaAttentionStateStore
from models.media_attention import MediaAttentionMediaType, PipelineSnapshot, PipelineStage
from test_media_attention_service import (
    FakeOverseerrService,
    FakePlexService,
    FakeRadarrService,
    FakeSabnzbdClient,
    FakeTmdbService,
)


class FakeDiscord:
    def __init__(self):
        self.sent = []
        self.updated = []
        self.resolved_updates = []

    async def send_media_attention_alert(self, alert, snapshot, stuck_minutes):
        self.sent.append((alert, snapshot, stuck_minutes))
        return type("Message", (), {"id": len(self.sent)})()

    async def update_media_attention_alert(
        self, message_id, alert, snapshot, stuck_minutes
    ):
        self.updated.append((message_id, alert, snapshot, stuck_minutes))
        return True

    async def update_resolved_media_attention_alert(self, message_id, alert, snapshot):
        self.resolved_updates.append((message_id, alert, snapshot))
        return True


class MediaAttentionMonitorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
        self.request = {
            "id": 123,
            "type": "movie",
            "status": 2,
            "media": {"tmdbId": 353491, "title": "The Martian"},
        }
        self.overseerr = FakeOverseerrService([self.request])
        self.radarr = FakeRadarrService()
        self.tmdb = FakeTmdbService(True)
        self.attention = MediaAttentionService(
            MediaAttentionStateStore(Path(self.temp.name) / "tracking.json"),
            self.overseerr,
            self.radarr,
            self.tmdb,
            FakeSabnzbdClient(),
            FakePlexService(),
        )
        self.alert_store = MediaAttentionAlertStore(
            Path(self.temp.name) / "alerts.json"
        )
        self.discord = FakeDiscord()
        self.previous_stall_minutes = Config.MEDIA_ATTENTION_STALL_MINUTES
        Config.MEDIA_ATTENTION_STALL_MINUTES = 20
        self.monitor = MediaAttentionMonitorService(
            self.attention, self.alert_store, self.discord
        )

    def tearDown(self):
        Config.MEDIA_ATTENTION_STALL_MINUTES = self.previous_stall_minutes
        self.temp.cleanup()

    def test_default_stall_threshold_is_twenty_minutes(self):
        self.assertEqual(self.monitor.stall_threshold, timedelta(minutes=20))

    async def test_custom_stall_threshold_is_respected(self):
        Config.MEDIA_ATTENTION_STALL_MINUTES = 5
        self.monitor = MediaAttentionMonitorService(
            self.attention, self.alert_store, self.discord
        )
        await self.monitor.run_cycle(self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=4))
        self.assertEqual(self.discord.sent, [])
        await self.monitor.run_cycle(self.now + timedelta(minutes=5))
        self.assertEqual(len(self.discord.sent), 1)

    async def test_stalled_movie_uses_radarr_title_when_request_title_is_missing(self):
        self.request["media"].pop("title")
        self.radarr.movies = [
            {
                "id": 1,
                "tmdbId": self.request["media"]["tmdbId"],
                "title": "The Martian",
            }
        ]

        await self.monitor.run_cycle(self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=20))

        alert, snapshot, _ = self.discord.sent[0]
        self.assertEqual(snapshot.title, "The Martian")
        self.assertEqual(alert.title, "The Martian")

    async def test_no_alert_before_threshold_then_create_without_duplicates(self):
        await self.monitor.run_cycle(self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=19))
        self.assertEqual(self.discord.sent, [])
        await self.monitor.run_cycle(self.now + timedelta(minutes=20))
        self.assertEqual(len(self.discord.sent), 1)
        await self.monitor.run_cycle(self.now + timedelta(minutes=21))
        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(len(self.discord.updated), 1)

    async def test_routine_evaluation_and_cycle_logs_are_debug(self):
        with self.assertLogs("media-butler", level="DEBUG") as logs:
            await self.monitor.run_cycle(self.now)

        output = "\n".join(logs.output)
        self.assertIn("DEBUG:media-butler:Media Attention movie=", output)
        self.assertIn("DEBUG:media-butler:Media Attention cycle:", output)

    async def test_alert_lifecycle_logs_remain_info(self):
        with self.assertLogs("media-butler", level="INFO") as logs:
            await self.monitor.run_cycle(self.now)
            await self.monitor.run_cycle(self.now + timedelta(minutes=20))
            self.radarr.movies = [{"id": 1, "tmdbId": 353491}]
            await self.monitor.run_cycle(self.now + timedelta(minutes=21))

        output = "\n".join(logs.output)
        self.assertIn("INFO:media-butler:Media Attention created alert", output)
        self.assertIn("INFO:media-butler:Media Attention resolved alert", output)

    async def test_normal_pipeline_transitions_do_not_create_alert_history(self):
        self.radarr.movies = [{"id": 1, "tmdbId": 353491}]
        await self.monitor.run_cycle(self.now)

        self.radarr.movies = [{"id": 1, "tmdbId": 353491, "hasFile": True}]
        await self.monitor.run_cycle(self.now + timedelta(minutes=1))

        self.assertEqual(self.discord.sent, [])
        self.assertEqual(self.discord.resolved_updates, [])
        self.assertEqual(self.monitor.alerts, {})

    async def test_resolved_alert_updates_existing_discord_message(self):
        await self.monitor.run_cycle(self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=20))
        original_alert = next(iter(self.monitor.alerts.values()))
        self.assertTrue(self.alert_store.state_file.exists())

        self.radarr.movies = [{"id": 1, "tmdbId": 353491}]
        await self.monitor.run_cycle(self.now + timedelta(minutes=21))

        self.assertEqual(original_alert.status, "resolved")
        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(len(self.discord.resolved_updates), 1)
        message_id, resolved_alert, _ = self.discord.resolved_updates[0]
        self.assertEqual(message_id, original_alert.message_id)
        self.assertEqual(resolved_alert.message_id, original_alert.message_id)

    async def test_stage_progress_resolves_and_later_stall_creates_new_alert(self):
        await self.monitor.run_cycle(self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=20))
        self.radarr.movies = [{"id": 1, "tmdbId": 353491}]
        await self.monitor.run_cycle(self.now + timedelta(minutes=21))
        self.assertEqual(list(self.monitor.alerts.values())[0].status, "resolved")
        await self.monitor.run_cycle(self.now + timedelta(minutes=41))
        self.assertEqual(len(self.discord.sent), 2)

    async def test_active_alert_is_reused_after_restart(self):
        await self.monitor.run_cycle(self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=20))
        original_alert = next(iter(self.monitor.alerts.values()))
        persisted_alerts = json.loads(self.alert_store.state_file.read_text())
        for alert in persisted_alerts["alerts"].values():
            alert.pop("media_key")
        self.alert_store.state_file.write_text(json.dumps(persisted_alerts))

        reloaded_attention = MediaAttentionService(
            MediaAttentionStateStore(Path(self.temp.name) / "tracking.json"),
            self.overseerr,
            self.radarr,
            self.tmdb,
            FakeSabnzbdClient(),
            FakePlexService(),
        )
        restarted = MediaAttentionMonitorService(
            reloaded_attention, self.alert_store, self.discord
        )
        await restarted.run_cycle(self.now + timedelta(minutes=21))

        active_alerts = [
            alert for alert in restarted.alerts.values() if alert.status == "active"
        ]
        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(len(self.discord.updated), 1)
        self.assertEqual(len(active_alerts), 1)
        self.assertEqual(active_alerts[0].message_id, original_alert.message_id)
        self.assertEqual(
            reloaded_attention.tracked_media["movie:tmdb:353491"].stall_generation, 1
        )

    async def test_unavailable_movie_never_enters_monitoring(self):
        self.tmdb.digitally_available = False
        snapshots = await self.monitor.run_cycle(self.now)
        self.assertEqual(snapshots, [])
        self.assertEqual(self.monitor.alerts, {})

    async def test_tv_threshold_lifecycle_and_terminal_stage(self):
        previous = Config.MEDIA_ATTENTION_TV_STALL_MINUTES
        Config.MEDIA_ATTENTION_TV_STALL_MINUTES = 120
        snapshot = PipelineSnapshot(
            media_key="tv:tmdb:9", media_type=MediaAttentionMediaType.TV,
            tmdb_id=9, request_id=9, title="Weekly", stage=PipelineStage.SONARR_SEARCHING,
            stage_detail="Searching", episode_progress=None,
        )
        self.attention.evaluate_requested_movies = lambda now: []
        self.attention.evaluate_requested_tv = lambda now: [snapshot]
        self.attention.evaluate_snapshot(snapshot, self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=119))
        self.assertEqual(self.discord.sent, [])
        await self.monitor.run_cycle(self.now + timedelta(minutes=120))
        self.assertEqual(len(self.discord.sent), 1)
        await self.monitor.run_cycle(self.now + timedelta(minutes=121))
        self.assertEqual(len(self.monitor.alerts), 1)
        caught_up = PipelineSnapshot(
            media_key="tv:tmdb:9", media_type=MediaAttentionMediaType.TV,
            tmdb_id=9, request_id=9, title="Weekly", stage=PipelineStage.SERIES_CAUGHT_UP,
            stage_detail="Caught up",
        )
        self.attention.evaluate_requested_tv = lambda now: [caught_up]
        self.attention.evaluate_snapshot(caught_up, self.now + timedelta(minutes=122))
        await self.monitor.run_cycle(self.now + timedelta(minutes=122))
        self.assertEqual(next(iter(self.monitor.alerts.values())).status, "resolved")
        Config.MEDIA_ATTENTION_TV_STALL_MINUTES = previous

    async def test_tv_active_alert_reuses_after_restart_then_next_generation(self):
        previous = Config.MEDIA_ATTENTION_TV_STALL_MINUTES
        Config.MEDIA_ATTENTION_TV_STALL_MINUTES = 5
        try:
            self.monitor = MediaAttentionMonitorService(self.attention, self.alert_store, self.discord)
            snapshot = PipelineSnapshot("tv:tmdb:9", MediaAttentionMediaType.TV, 9, 9, "Weekly", PipelineStage.SONARR_SEARCHING, "Searching")
            self.attention.evaluate_requested_movies = lambda now: []
            self.attention.evaluate_requested_tv = lambda now: [snapshot]
            self.attention.evaluate_snapshot(snapshot, self.now)
            self.attention.state_store.save(self.attention.tracked_media)
            await self.monitor.run_cycle(self.now + timedelta(minutes=5))
            self.assertEqual(len(self.discord.sent), 1)
            alert_key = "tv:tmdb:9:stall:1"
            message_id = self.monitor.alerts[alert_key].message_id
            restarted_attention = MediaAttentionService(MediaAttentionStateStore(Path(self.temp.name) / "tracking.json"), self.overseerr, self.radarr, self.tmdb, FakeSabnzbdClient(), FakePlexService())
            restarted_attention.evaluate_requested_movies = lambda now: []
            restarted_attention.evaluate_requested_tv = lambda now: [snapshot]
            restarted = MediaAttentionMonitorService(restarted_attention, self.alert_store, self.discord)
            await restarted.run_cycle(self.now + timedelta(minutes=6))
            self.assertEqual(len(self.discord.sent), 1)
            self.assertEqual(restarted.alerts[alert_key].message_id, message_id)
            self.assertEqual(len(self.discord.updated), 1)
            progress = PipelineSnapshot("tv:tmdb:9", MediaAttentionMediaType.TV, 9, 9, "Weekly", PipelineStage.DOWNLOADING, "Downloading", sab_evidence={"active": True, "percent": 1})
            restarted_attention.evaluate_requested_tv = lambda now: [progress]
            restarted_attention.evaluate_snapshot(progress, self.now + timedelta(minutes=7))
            await restarted.run_cycle(self.now + timedelta(minutes=7))
            self.assertEqual(restarted.alerts[alert_key].status, "resolved")
            self.assertEqual(len(self.discord.resolved_updates), 1)
            await restarted.run_cycle(self.now + timedelta(minutes=12))
            self.assertIn("tv:tmdb:9:stall:2", restarted.alerts)
        finally:
            Config.MEDIA_ATTENTION_TV_STALL_MINUTES = previous


class MutableSonarr:
    def __init__(self, episodes):
        self.episodes = episodes
        self.queue = []
        self.refreshes = []
        self.series = [{"id": 90, "tmdbId": 9, "title": "Weekly"}]

    def get_series(self):
        return self.series

    def get_episodes(self, series_id, refresh=False):
        self.refreshes.append(refresh)
        return self.episodes

    def get_queue(self):
        return self.queue


class RecordingAlertStore:
    def __init__(self, alerts):
        self.alerts = alerts
        self.saved = []

    def load(self):
        return self.alerts

    def save(self, alerts):
        self.saved.append(copy.deepcopy(alerts))


class EvaluatorIsolationTests(unittest.IsolatedAsyncioTestCase):
    def _alert(self, key, media_type):
        from models.media_attention import MediaAttentionAlert
        return MediaAttentionAlert(key, media_type, 1, 1, "Existing", PipelineStage.SONARR_SEARCHING, "active", datetime(2026, 7, 1, tzinfo=timezone.utc), message_id=77, details_fingerprint="unchanged")

    def _attention_with_snapshot(self, snapshot, now):
        temp = tempfile.TemporaryDirectory()
        service = MediaAttentionService(MediaAttentionStateStore(Path(temp.name) / "tracking.json"), FakeOverseerrService([]), FakeRadarrService(), TvTmdb(True), FakeSabnzbdClient(), FakePlexService(), MutableSonarr([]))
        service.evaluate_snapshot(snapshot, now - timedelta(minutes=30))
        return temp, service

    async def test_tv_failure_preserves_tv_alert_and_processes_movie(self):
        now = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
        movie = PipelineSnapshot("movie:tmdb:2", MediaAttentionMediaType.MOVIE, 2, 2, "Movie", PipelineStage.ARR_SEARCHING, "Searching")
        temp, service = self._attention_with_snapshot(movie, now)
        existing = self._alert("tv:tmdb:1", MediaAttentionMediaType.TV)
        store = RecordingAlertStore({"tv:tmdb:1:stall:1": existing})
        calls = []
        service.evaluate_requested_movies = lambda at: calls.append("movie") or [movie]
        def fail(at): calls.append("tv"); raise RuntimeError("Sonarr unavailable")
        service.evaluate_requested_tv = fail
        monitor = MediaAttentionMonitorService(service, store, FakeDiscord())
        with self.assertLogs("media-butler", "ERROR") as logs:
            result = await monitor.run_cycle(now)
        self.assertEqual(result, [movie]); self.assertEqual(calls, ["movie", "tv"])
        self.assertIn("TV evaluation failed", "\n".join(logs.output))
        self.assertIs(monitor.alerts["tv:tmdb:1:stall:1"], existing)
        self.assertEqual(len(store.saved), 1); self.assertIn("tv:tmdb:1:stall:1", store.saved[0])
        temp.cleanup()

    async def test_movie_failure_preserves_movie_alert_and_processes_tv(self):
        now = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
        tv = PipelineSnapshot("tv:tmdb:2", MediaAttentionMediaType.TV, 2, 2, "TV", PipelineStage.SONARR_SEARCHING, "Searching")
        temp, service = self._attention_with_snapshot(tv, now)
        existing = self._alert("movie:tmdb:1", MediaAttentionMediaType.MOVIE)
        store = RecordingAlertStore({"movie:tmdb:1:stall:1": existing})
        calls = []
        def fail(at): calls.append("movie"); raise RuntimeError("Radarr unavailable")
        service.evaluate_requested_movies = fail
        service.evaluate_requested_tv = lambda at: calls.append("tv") or [tv]
        monitor = MediaAttentionMonitorService(service, store, FakeDiscord())
        with self.assertLogs("media-butler", "ERROR") as logs:
            result = await monitor.run_cycle(now)
        self.assertEqual(result, [tv]); self.assertEqual(calls, ["movie", "tv"])
        self.assertIn("movie evaluation failed", "\n".join(logs.output))
        self.assertIs(monitor.alerts["movie:tmdb:1:stall:1"], existing)
        self.assertEqual(len(store.saved), 1); self.assertIn("movie:tmdb:1:stall:1", store.saved[0])
        temp.cleanup()

    async def test_both_evaluator_failures_preserve_alerts_and_save(self):
        now = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
        temp, service = self._attention_with_snapshot(PipelineSnapshot("movie:tmdb:2", MediaAttentionMediaType.MOVIE, 2, 2, "Movie", PipelineStage.ARR_SEARCHING, "Searching"), now)
        alerts = {"movie:tmdb:1:stall:1": self._alert("movie:tmdb:1", MediaAttentionMediaType.MOVIE), "tv:tmdb:1:stall:1": self._alert("tv:tmdb:1", MediaAttentionMediaType.TV)}
        store = RecordingAlertStore(alerts)
        calls = []
        def movie(at): calls.append("movie"); raise RuntimeError("movie down")
        def tv(at): calls.append("tv"); raise RuntimeError("tv down")
        service.evaluate_requested_movies, service.evaluate_requested_tv = movie, tv
        monitor = MediaAttentionMonitorService(service, store, FakeDiscord())
        with self.assertLogs("media-butler", "ERROR") as logs:
            self.assertEqual(await monitor.run_cycle(now), [])
        self.assertEqual(calls, ["movie", "tv"]); self.assertEqual(len(store.saved), 1)
        self.assertIn("movie evaluation failed", "\n".join(logs.output)); self.assertIn("TV evaluation failed", "\n".join(logs.output))
        self.assertEqual(store.saved[0], alerts)
        temp.cleanup()

    async def test_both_successful_evaluators_process_each_snapshot_once(self):
        now = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
        movie = PipelineSnapshot("movie:tmdb:3", MediaAttentionMediaType.MOVIE, 3, 3, "Movie", PipelineStage.ARR_SEARCHING, "Searching")
        tv = PipelineSnapshot("tv:tmdb:4", MediaAttentionMediaType.TV, 4, 4, "TV", PipelineStage.SONARR_SEARCHING, "Searching")
        temp, service = self._attention_with_snapshot(movie, now)
        service.evaluate_snapshot(tv, now - timedelta(minutes=30))
        calls, processed = [], []
        service.evaluate_requested_movies = lambda at: calls.append("movie") or [movie]
        service.evaluate_requested_tv = lambda at: calls.append("tv") or [tv]
        store = RecordingAlertStore({})
        monitor = MediaAttentionMonitorService(service, store, FakeDiscord())
        original = monitor._evaluate_snapshot
        async def record(snapshot, at):
            processed.append(snapshot.media_key)
            await original(snapshot, at)
        monitor._evaluate_snapshot = record
        self.assertEqual(await monitor.run_cycle(now), [movie, tv])
        self.assertEqual(calls, ["movie", "tv"]); self.assertEqual(processed, [movie.media_key, tv.media_key])
        self.assertEqual(len(store.saved), 1)
        temp.cleanup()


class TvTmdb(FakeTmdbService):
    def tv_has_digital_availability(self, tmdb_id):
        return self.digitally_available


class WeeklyTvLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_waiting_for_sonarr_real_lifecycle(self):
        temp = tempfile.TemporaryDirectory()
        previous = Config.MEDIA_ATTENTION_TV_STALL_MINUTES
        Config.MEDIA_ATTENTION_TV_STALL_MINUTES = 5
        try:
            now = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
            sonarr = MutableSonarr([])
            sonarr.series = []
            attention = MediaAttentionService(MediaAttentionStateStore(Path(temp.name) / "tracking.json"), FakeOverseerrService([{"id": 9, "type": "tv", "status": 2, "media": {"tmdbId": 9, "title": "Weekly"}}]), FakeRadarrService(), TvTmdb(True), FakeSabnzbdClient(), FakePlexService(), sonarr)
            discord = FakeDiscord()
            monitor = MediaAttentionMonitorService(attention, MediaAttentionAlertStore(Path(temp.name) / "alerts.json"), discord)
            initial = await monitor.run_cycle(now)
            snapshot = next(item for item in initial if item.media_key == "tv:tmdb:9")
            self.assertEqual(snapshot.stage, PipelineStage.WAITING_FOR_SONARR)
            self.assertIsNone(snapshot.episode_progress)
            await monitor.run_cycle(now + timedelta(minutes=4))
            self.assertEqual(discord.sent, [])
            await monitor.run_cycle(now + timedelta(minutes=5))
            self.assertEqual(len(discord.sent), 1)
            self.assertIn("Unavailable until the series reaches Sonarr", str(discord.sent[0][1].episode_progress) if discord.sent[0][1].episode_progress else "Unavailable until the series reaches Sonarr")
            sonarr.series = [{"id": 90, "tmdbId": 9, "title": "Weekly"}]
            sonarr.episodes = [{"id": 101, "seasonNumber": 1, "episodeNumber": 1, "airDateUtc": "2026-07-01T00:00:00Z", "hasFile": False}]
            appeared = next(item for item in await monitor.run_cycle(now + timedelta(minutes=6)) if item.media_key == "tv:tmdb:9")
            self.assertEqual(appeared.stage, PipelineStage.SONARR_SEARCHING)
            self.assertIsNotNone(appeared.episode_progress)
            self.assertFalse(any(alert.status == "active" for alert in monitor.alerts.values()))
        finally:
            Config.MEDIA_ATTENTION_TV_STALL_MINUTES = previous
            temp.cleanup()

    async def test_real_weekly_release_lifecycle_uses_tv_evaluator(self):
        temp = tempfile.TemporaryDirectory()
        previous = Config.MEDIA_ATTENTION_TV_STALL_MINUTES
        Config.MEDIA_ATTENTION_TV_STALL_MINUTES = 120
        try:
            start = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
            sonarr = MutableSonarr([
                {"id": 101, "seasonNumber": 1, "episodeNumber": 1, "airDateUtc": "2026-07-01T00:00:00Z", "hasFile": True},
                {"id": 102, "seasonNumber": 1, "episodeNumber": 2, "airDateUtc": "2026-07-21T13:00:00Z", "hasFile": False},
            ])
            attention = MediaAttentionService(
                MediaAttentionStateStore(Path(temp.name) / "tracking.json"),
                FakeOverseerrService([{"id": 9, "type": "tv", "status": 2, "media": {"tmdbId": 9, "title": "Weekly"}}]),
                FakeRadarrService(), TvTmdb(True), FakeSabnzbdClient(), FakePlexService(), sonarr,
            )
            alerts = MediaAttentionAlertStore(Path(temp.name) / "alerts.json")
            discord = FakeDiscord()
            monitor = MediaAttentionMonitorService(attention, alerts, discord)

            before = attention.evaluate_requested_tv(start)
            self.assertEqual(len(before), 1)
            self.assertEqual(before[0].stage, PipelineStage.SERIES_CAUGHT_UP)
            self.assertEqual(before[0].episode_progress.released_episode_keys, ("S01E01",))
            key = "tv:tmdb:9"
            self.assertEqual(set(attention.tracked_media), {key})
            caught_fingerprint = before[0].progress_fingerprint

            release = start + timedelta(hours=2)
            snapshots = await monitor.run_cycle(release)
            snapshot = next(item for item in snapshots if item.media_key == key)
            self.assertEqual(snapshot.stage, PipelineStage.SONARR_SEARCHING)
            self.assertEqual(snapshot.episode_progress.missing_episode_keys, ("S01E02",))
            self.assertNotEqual(snapshot.progress_fingerprint, caught_fingerprint)
            self.assertEqual(attention.tracked_media[key].last_progress_at, release)
            self.assertEqual(discord.sent, [])

            await monitor.run_cycle(release + timedelta(minutes=119))
            self.assertEqual(discord.sent, [])
            await monitor.run_cycle(release + timedelta(minutes=120))
            self.assertEqual(len(discord.sent), 1)
            await monitor.run_cycle(release + timedelta(minutes=121))
            self.assertEqual(len(discord.sent), 1)
            self.assertEqual(len(discord.updated), 1)

            sonarr.queue = [{"seriesId": 90, "episodeId": 102, "downloadId": "weekly", "status": "downloading", "size": 100, "sizeleft": 50, "progress": 50}]
            downloading_at = release + timedelta(minutes=122)
            downloading = next(item for item in await monitor.run_cycle(downloading_at) if item.media_key == key)
            self.assertEqual(downloading.stage, PipelineStage.DOWNLOADING)
            self.assertEqual(attention.tracked_media[key].last_progress_at, downloading_at)
            self.assertFalse(any(alert.status == "active" for alert in monitor.alerts.values()))
            sonarr.queue[0]["sizeleft"] = 25
            progressed_at = downloading_at + timedelta(minutes=1)
            await monitor.run_cycle(progressed_at)
            self.assertEqual(attention.tracked_media[key].last_progress_at, progressed_at)

            sonarr.episodes[1]["hasFile"] = True
            sonarr.queue = []
            caught = next(item for item in await monitor.run_cycle(progressed_at + timedelta(minutes=1)) if item.media_key == key)
            self.assertEqual(caught.stage, PipelineStage.SERIES_CAUGHT_UP)
            self.assertEqual(caught.episode_progress.arr_imported_episode_keys, ("S01E01", "S01E02"))

            sonarr.episodes.append({"id": 103, "seasonNumber": 1, "episodeNumber": 3, "airDateUtc": "2026-07-22T00:00:00Z", "hasFile": False})
            self.assertEqual(next(item for item in await monitor.run_cycle(progressed_at + timedelta(minutes=2) ) if item.media_key == key).stage, PipelineStage.SERIES_CAUGHT_UP)
            third_release = datetime(2026, 7, 22, 0, 1, tzinfo=timezone.utc)
            third = next(item for item in await monitor.run_cycle(third_release) if item.media_key == key)
            self.assertEqual(third.stage, PipelineStage.SONARR_SEARCHING)
            self.assertEqual(attention.tracked_media[key].last_progress_at, third_release)
            self.assertEqual(set(attention.tracked_media), {key})
            self.assertTrue(all("S01E" not in alert_key for alert_key in monitor.alerts))
            self.assertTrue(all(sonarr.refreshes))
        finally:
            Config.MEDIA_ATTENTION_TV_STALL_MINUTES = previous
            temp.cleanup()


class MediaAttentionStateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def test_tv_tracked_media_reloads_all_progress_fields(self):
        path = Path(self.temp.name) / "tracking.json"
        store = MediaAttentionStateStore(path)
        now = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
        service = MediaAttentionService(store, FakeOverseerrService([]), FakeRadarrService(), TvTmdb(True), FakeSabnzbdClient(), FakePlexService(), MutableSonarr([]))
        snapshot = PipelineSnapshot("tv:tmdb:9", MediaAttentionMediaType.TV, 9, 7, "Weekly", PipelineStage.SONARR_SEARCHING, "Searching")
        service.evaluate_snapshot(snapshot, now)
        tracked = service.tracked_media[snapshot.media_key]
        tracked.stall_generation = 3
        store.save(service.tracked_media)
        reloaded = MediaAttentionService(store, FakeOverseerrService([]), FakeRadarrService(), TvTmdb(True), FakeSabnzbdClient(), FakePlexService(), MutableSonarr([]))
        loaded = reloaded.tracked_media["tv:tmdb:9"]
        self.assertEqual(loaded.media_type, MediaAttentionMediaType.TV)
        self.assertEqual(loaded.current_stage, PipelineStage.SONARR_SEARCHING)
        self.assertIsNone(loaded.previous_stage)
        self.assertEqual(loaded.first_seen_at, now)
        self.assertEqual(loaded.last_progress_at, now)
        self.assertEqual(loaded.last_progress_fingerprint, snapshot.progress_fingerprint)
        self.assertEqual(loaded.stall_generation, 3)
        self.assertFalse(reloaded.evaluate_snapshot(snapshot, now + timedelta(minutes=1)))
        self.assertEqual(loaded.last_progress_at, now)

    def test_legacy_tracking_without_first_seen_uses_last_progress(self):
        path = Path(self.temp.name) / "tracking.json"
        timestamp = "2026-07-21T12:00:00+00:00"
        path.write_text(json.dumps({"version": 1, "tracked_media": {"movie:tmdb:1": {
            "media_type": "movie", "tmdb_id": 1, "request_id": 1, "title": "Old",
            "current_stage": "arr_searching", "previous_stage": None,
            "last_progress_at": timestamp, "last_progress_fingerprint": "x", "stall_generation": 0,
        }}}))
        tracked = MediaAttentionStateStore(path).load()["movie:tmdb:1"]
        self.assertEqual(tracked.first_seen_at, tracked.last_progress_at)

    def test_missing_empty_and_whitespace_files_load_silently(self):
        for store_type, filename in (
            (MediaAttentionStateStore, "tracking.json"),
            (MediaAttentionAlertStore, "alerts.json"),
        ):
            path = Path(self.temp.name) / filename
            store = store_type(path)
            with self.assertNoLogs("media-butler", level="WARNING"):
                self.assertEqual(store.load(), {})
                path.write_text("")
                self.assertEqual(store.load(), {})
                path.write_text(" \n\t ")
                self.assertEqual(store.load(), {})

    def test_valid_state_files_load(self):
        tracking_path = Path(self.temp.name) / "tracking.json"
        tracking_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "tracked_media": {
                        "movie:tmdb:1": {
                            "media_type": "movie",
                            "tmdb_id": 1,
                            "request_id": 2,
                            "title": "Movie",
                            "current_stage": "waiting_for_arr",
                            "previous_stage": None,
                            "last_progress_at": self._timestamp(),
                            "last_progress_fingerprint": "fingerprint",
                            "stall_generation": 0,
                        }
                    },
                }
            )
        )
        alert_path = Path(self.temp.name) / "alerts.json"
        alert_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "alerts": {
                        "movie:tmdb:1:stall:1": {
                            "media_type": "movie",
                            "tmdb_id": 1,
                            "request_id": 2,
                            "title": "Movie",
                            "stage": "waiting_for_arr",
                            "status": "active",
                            "created_at": self._timestamp(),
                            "message_id": None,
                            "resolved_at": None,
                            "details_fingerprint": "fingerprint",
                        }
                    },
                }
            )
        )

        self.assertIn("movie:tmdb:1", MediaAttentionStateStore(tracking_path).load())
        self.assertIn(
            "movie:tmdb:1:stall:1", MediaAttentionAlertStore(alert_path).load()
        )

    def test_malformed_nonempty_state_files_warn_and_fall_back(self):
        for store_type, filename in (
            (MediaAttentionStateStore, "tracking.json"),
            (MediaAttentionAlertStore, "alerts.json"),
        ):
            path = Path(self.temp.name) / filename
            path.write_text("not json")
            with self.assertLogs("media-butler", level="WARNING") as logs:
                self.assertEqual(store_type(path).load(), {})
            self.assertIn("Failed to load", "\n".join(logs.output))

    @staticmethod
    def _timestamp():
        return "2026-07-21T12:00:00+00:00"
