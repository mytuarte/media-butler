import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import Config
from services.media_attention_alert_store import MediaAttentionAlertStore
from services.media_attention_monitor_service import MediaAttentionMonitorService
from services.media_attention_service import MediaAttentionService
from services.media_attention_state_store import MediaAttentionStateStore
from test_media_attention_service import (FakeOverseerrService, FakePlexService,
    FakeRadarrService, FakeSabnzbdClient, FakeTmdbService)


class FakeDiscord:
    def __init__(self): self.sent = []; self.updated = []
    async def send_media_attention_alert(self, alert, snapshot, stuck_minutes):
        self.sent.append((alert, snapshot, stuck_minutes))
        return type("Message", (), {"id": len(self.sent)})()
    async def update_media_attention_alert(self, message_id, alert, snapshot, stuck_minutes):
        self.updated.append((message_id, alert, snapshot, stuck_minutes))
        return True


class MediaAttentionMonitorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
        self.request = {"id": 123, "type": "movie", "status": 2,
                        "media": {"tmdbId": 353491, "title": "The Martian"}}
        self.overseerr = FakeOverseerrService([self.request])
        self.radarr = FakeRadarrService()
        self.tmdb = FakeTmdbService(True)
        self.attention = MediaAttentionService(
            MediaAttentionStateStore(Path(self.temp.name) / "tracking.json"), self.overseerr,
            self.radarr, self.tmdb, FakeSabnzbdClient(), FakePlexService())
        self.alert_store = MediaAttentionAlertStore(Path(self.temp.name) / "alerts.json")
        self.discord = FakeDiscord()
        self.previous_stall_minutes = Config.MEDIA_ATTENTION_STALL_MINUTES
        Config.MEDIA_ATTENTION_STALL_MINUTES = 20
        self.monitor = MediaAttentionMonitorService(self.attention, self.alert_store, self.discord)

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
        self.radarr.movies = [{
            "id": 1,
            "tmdbId": self.request["media"]["tmdbId"],
            "title": "The Martian",
        }]

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

    async def test_stage_progress_resolves_and_later_stall_creates_new_alert(self):
        await self.monitor.run_cycle(self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=20))
        self.radarr.movies = [{"id": 1, "tmdbId": 353491}]
        await self.monitor.run_cycle(self.now + timedelta(minutes=21))
        self.assertEqual(list(self.monitor.alerts.values())[0].status, "resolved")
        await self.monitor.run_cycle(self.now + timedelta(minutes=41))
        self.assertEqual(len(self.discord.sent), 2)

    async def test_active_alert_survives_restart(self):
        await self.monitor.run_cycle(self.now)
        await self.monitor.run_cycle(self.now + timedelta(minutes=20))
        restarted = MediaAttentionMonitorService(self.attention, self.alert_store, self.discord)
        self.assertEqual(len(restarted.alerts), 1)
        self.assertEqual(next(iter(restarted.alerts.values())).status, "active")

    async def test_unavailable_movie_never_enters_monitoring(self):
        self.tmdb.digitally_available = False
        snapshots = await self.monitor.run_cycle(self.now)
        self.assertEqual(snapshots, [])
        self.assertEqual(self.monitor.alerts, {})
