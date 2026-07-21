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

    def create_service(self, request, digitally_available, movies=None):
        return MediaAttentionService(
            state_store=self.store,
            overseerr=FakeOverseerrService([request]),
            radarr=FakeRadarrService(movies),
            tmdb=FakeTmdbService(digitally_available),
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
