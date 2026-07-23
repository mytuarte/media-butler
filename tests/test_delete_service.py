import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from models.overseerr_request import OverseerrRequest
from services.delete_service import DeleteService
from services.registry import services


class FakeRadarrService:
    def __init__(self):
        self.deleted_movie_id = None

    def delete_movie(self, movie_id):
        self.deleted_movie_id = movie_id


class FakeOverseerrService:
    def __init__(self, request, request_error=None, media_error=None):
        self.request = request
        self.request_error = request_error
        self.media_error = media_error
        self.deleted_request_id = None
        self.cleared_media_id = None
        self.request_refresh = None
        self.cached_request = None
        self.cache_invalidated = 0
        self.calls = []

    def get_request(self, tmdb_id, refresh=False):
        self.request_refresh = refresh
        return self.request if refresh else self.cached_request

    def delete_request(self, request_id):
        self.calls.append("delete_request")
        self.deleted_request_id = request_id
        if self.request_error:
            raise self.request_error

    def clear_media_data(self, media_id):
        self.calls.append("clear_media_data")
        self.cleared_media_id = media_id
        if self.media_error:
            raise self.media_error

    def invalidate_request_cache(self):
        self.cache_invalidated += 1


class DeleteServiceTests(unittest.TestCase):
    def movie(self):
        return SimpleNamespace(
            id=42,
            title="The Iron Giant",
            media_type="movie",
            tmdb_id=10386,
        )

    def request(self):
        return OverseerrRequest(
            id=7,
            status=2,
            media_status=5,
            requester="Mike",
            requester_discord_id=None,
            requested_date=None,
            raw={},
            media_id=9,
        )

    def test_delete_refreshes_and_clears_new_overseerr_request_data(self):
        radarr = FakeRadarrService()
        overseerr = FakeOverseerrService(self.request())

        with patch.object(services, "radarr", radarr), patch.object(
            services, "overseerr", overseerr
        ):
            result = DeleteService().delete(self.movie())

        self.assertEqual(radarr.deleted_movie_id, 42)
        self.assertEqual(overseerr.deleted_request_id, 7)
        self.assertEqual(overseerr.cleared_media_id, 9)
        self.assertTrue(overseerr.request_refresh)
        self.assertEqual(
            overseerr.calls,
            ["clear_media_data", "delete_request"],
        )
        self.assertTrue(result.overseerr_deleted)

    def test_delete_continues_when_overseerr_data_is_already_removed(self):
        response = SimpleNamespace(status_code=404)
        error = requests.HTTPError(response=response)
        radarr = FakeRadarrService()
        overseerr = FakeOverseerrService(
            self.request(),
            request_error=error,
            media_error=error,
        )

        with patch.object(services, "radarr", radarr), patch.object(
            services, "overseerr", overseerr
        ):
            result = DeleteService().delete(self.movie())

        self.assertEqual(overseerr.deleted_request_id, 7)
        self.assertEqual(overseerr.cleared_media_id, 9)
        self.assertEqual(overseerr.cache_invalidated, 2)
        self.assertTrue(result.overseerr_deleted)

    def test_delete_continues_when_overseerr_request_no_longer_exists(self):
        radarr = FakeRadarrService()
        overseerr = FakeOverseerrService(None)

        with patch.object(services, "radarr", radarr), patch.object(
            services, "overseerr", overseerr
        ):
            result = DeleteService().delete(self.movie())

        self.assertEqual(radarr.deleted_movie_id, 42)
        self.assertIsNone(overseerr.deleted_request_id)
        self.assertIsNone(overseerr.cleared_media_id)
        self.assertFalse(result.overseerr_deleted)

    def test_delete_raises_for_genuine_overseerr_api_errors(self):
        response = SimpleNamespace(status_code=500)
        error = requests.HTTPError(response=response)
        radarr = FakeRadarrService()
        overseerr = FakeOverseerrService(self.request(), media_error=error)

        with patch.object(services, "radarr", radarr), patch.object(
            services, "overseerr", overseerr
        ):
            with self.assertRaises(requests.HTTPError):
                DeleteService().delete(self.movie())

        self.assertEqual(overseerr.calls, ["clear_media_data"])

    def test_delete_warns_when_overseerr_media_id_is_missing(self):
        request = self.request()
        request.media_id = None
        radarr = FakeRadarrService()
        overseerr = FakeOverseerrService(request)

        with patch.object(services, "radarr", radarr), patch.object(
            services, "overseerr", overseerr
        ), self.assertLogs("media-butler", level="WARNING") as logs:
            result = DeleteService().delete(self.movie())

        self.assertIn("media ID is missing", "\n".join(logs.output))
        self.assertEqual(overseerr.calls, ["delete_request"])
        self.assertTrue(result.overseerr_deleted)

    def test_delete_logs_genuine_api_failures_at_error_level(self):
        response = SimpleNamespace(status_code=500)
        error = requests.HTTPError(response=response)
        radarr = FakeRadarrService()
        overseerr = FakeOverseerrService(self.request(), media_error=error)

        with patch.object(services, "radarr", radarr), patch.object(
            services, "overseerr", overseerr
        ), self.assertLogs("media-butler", level="ERROR") as logs:
            with self.assertRaises(requests.HTTPError):
                DeleteService().delete(self.movie())

        self.assertIn(
            "ERROR:media-butler:Overseerr media data cleanup failed",
            "\n".join(logs.output),
        )


if __name__ == "__main__":
    unittest.main()
