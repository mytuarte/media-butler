import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from models.media_attention import PipelineStage
from services.media_attention_service import MediaAttentionService
from services.media_attention_state_store import MediaAttentionStateStore


class FakeOverseerrService:
    def __init__(self, requests):
        self.requests = requests

    def get_requests(self):
        return {"results": self.requests}


class FakeRadarrService:
    def __init__(self, movies=None):
        self.movies = movies or []

    def get_movies(self):
        return self.movies

    def get_history(self):
        return {"records": []}


class FakeSabnzbdClient:
    def __init__(self, queue=None, history=None):
        self.queue = queue or []
        self.history = history or []

    def get_queue(self):
        return {"queue": {"slots": self.queue}}

    def get_history(self):
        return {"history": {"slots": self.history}}


class FakePlexService:
    def __init__(self, available=False):
        self.available = available

    def movie_is_available(self, tmdb_id, title):
        return self.available


class FakeTmdbService:
    def __init__(self, digitally_available):
        self.digitally_available = digitally_available
        self.calls = []

    def movie_has_digital_availability(self, tmdb_id):
        self.calls.append(tmdb_id)
        return self.digitally_available


class MediaAttentionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = MediaAttentionStateStore(
            Path(self.temporary_directory.name) / "media_attention.json"
        )
        self.now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def movie_request(status=2):
        return {
            "id": 123,
            "type": "movie",
            "status": status,
            "media": {"tmdbId": 353491, "title": "The Martian"},
        }

    def create_service(
        self,
        request,
        digitally_available,
        movies=None,
        queue=None,
        history=None,
        plex_available=False,
    ):
        return MediaAttentionService(
            state_store=self.store,
            overseerr=FakeOverseerrService([request]),
            radarr=FakeRadarrService(movies),
            tmdb=FakeTmdbService(digitally_available),
            sabnzbd=FakeSabnzbdClient(queue, history),
            plex=FakePlexService(plex_available),
        )

    def test_digitally_unavailable_movie_is_ignored(self):
        service = self.create_service(self.movie_request(), False)

        snapshots = service.evaluate_requested_movies(self.now)

        self.assertEqual(snapshots, [])
        self.assertEqual(service.tracked_media, {})

    def test_digitally_available_movie_creates_tracking_state(self):
        service = self.create_service(self.movie_request(), True)

        snapshots = service.evaluate_requested_movies(self.now)

        self.assertEqual(len(snapshots), 1)
        tracked = service.tracked_media["movie:tmdb:353491"]
        self.assertEqual(tracked.current_stage, PipelineStage.WAITING_FOR_ARR)
        self.assertEqual(tracked.last_progress_at, self.now)

    def test_same_snapshot_twice_does_not_count_as_progress(self):
        service = self.create_service(self.movie_request(), True)
        snapshot = service.capture_movie_snapshot(self.movie_request(), None)
        service.evaluate_snapshot(snapshot, self.now)

        later = datetime(2026, 7, 21, 12, 5, tzinfo=timezone.utc)
        progress_detected = service.evaluate_snapshot(snapshot, later)

        tracked = service.tracked_media[snapshot.media_key]
        self.assertFalse(progress_detected)
        self.assertEqual(tracked.last_progress_at, self.now)

    def test_stage_transition_counts_as_progress(self):
        service = self.create_service(self.movie_request(), True)
        waiting = service.capture_movie_snapshot(self.movie_request(), None)
        service.evaluate_snapshot(waiting, self.now)
        downloading = service.capture_movie_snapshot(
            self.movie_request(),
            {"id": 1, "tmdbId": 353491},
            sab_evidence={"active": True, "job_id": "sab-1", "percent": 1},
        )
        later = datetime(2026, 7, 21, 12, 5, tzinfo=timezone.utc)

        progress_detected = service.evaluate_snapshot(downloading, later)

        tracked = service.tracked_media[downloading.media_key]
        self.assertTrue(progress_detected)
        self.assertEqual(tracked.previous_stage, PipelineStage.WAITING_FOR_ARR)
        self.assertEqual(tracked.current_stage, PipelineStage.DOWNLOADING)
        self.assertEqual(tracked.last_progress_at, later)

    def test_movie_searching_in_radarr_is_arr_searching(self):
        service = self.create_service(
            self.movie_request(),
            True,
            [{"id": 1, "tmdbId": 353491, "monitored": True}],
        )

        snapshot = service.evaluate_requested_movies(self.now)[0]

        self.assertEqual(snapshot.stage, PipelineStage.ARR_SEARCHING)
        self.assertTrue(snapshot.arr_evidence["present"])

    def test_movie_downloading_records_sab_evidence(self):
        service = self.create_service(
            self.movie_request(),
            True,
            [{"id": 1, "tmdbId": 353491}],
            queue=[
                {
                    "filename": "The.Martian.2015.mkv",
                    "nzo_id": "sab-1",
                    "status": "Downloading",
                    "percentage": "62",
                    "mb": "1000",
                    "mbleft": "380",
                }
            ],
        )

        snapshot = service.evaluate_requested_movies(self.now)[0]

        self.assertEqual(snapshot.stage, PipelineStage.DOWNLOADING)
        self.assertEqual(snapshot.sab_evidence["download_id"], "sab-1")
        self.assertEqual(snapshot.sab_evidence["percent"], "62")

    def test_completed_download_without_import_is_import_pending(self):
        service = self.create_service(
            self.movie_request(),
            True,
            [{"id": 1, "tmdbId": 353491}],
            history=[
                {
                    "name": "The Martian 2015",
                    "nzo_id": "sab-1",
                    "status": "Completed",
                    "percentage": "100",
                }
            ],
        )

        snapshot = service.evaluate_requested_movies(self.now)[0]

        self.assertEqual(snapshot.stage, PipelineStage.IMPORT_PENDING)
        self.assertTrue(snapshot.sab_evidence["completed"])

    def test_imported_movie_missing_from_plex_is_plex_sync_pending(self):
        service = self.create_service(
            self.movie_request(),
            True,
            [{"id": 1, "tmdbId": 353491, "hasFile": True}],
        )

        snapshot = service.evaluate_requested_movies(self.now)[0]

        self.assertEqual(snapshot.stage, PipelineStage.PLEX_SYNC_PENDING)
        self.assertFalse(snapshot.plex_evidence["available"])

    def test_movie_in_plex_is_plex_available(self):
        service = self.create_service(
            self.movie_request(),
            True,
            [{"id": 1, "tmdbId": 353491, "hasFile": False}],
            plex_available=True,
        )

        snapshot = service.evaluate_requested_movies(self.now)[0]

        self.assertEqual(snapshot.stage, PipelineStage.PLEX_AVAILABLE)
        self.assertTrue(snapshot.plex_evidence["available"])

    def test_state_persists_and_reloads_correctly(self):
        service = self.create_service(self.movie_request(), True)
        service.evaluate_requested_movies(self.now)

        reloaded = MediaAttentionService(
            state_store=self.store,
            overseerr=FakeOverseerrService([]),
            radarr=FakeRadarrService(),
            tmdb=FakeTmdbService(True),
        )

        tracked = reloaded.tracked_media["movie:tmdb:353491"]
        self.assertEqual(tracked.tmdb_id, 353491)
        self.assertEqual(tracked.current_stage, PipelineStage.WAITING_FOR_ARR)
        self.assertEqual(tracked.last_progress_at, self.now)

    def test_future_or_theatrical_movie_does_not_enter_tracking(self):
        service = self.create_service(self.movie_request(), False)

        service.evaluate_requested_movies(self.now)

        self.assertNotIn("movie:tmdb:353491", service.tracked_media)


if __name__ == "__main__":
    unittest.main()
