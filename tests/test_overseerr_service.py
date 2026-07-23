import unittest
from unittest.mock import Mock

from config import Config
from services.overseerr_request_factory import OverseerrRequestFactory
from services.overseerr_service import OverseerrService


class OverseerrServiceTests(unittest.TestCase):
    def request_response(self, results):
        return {
            "results": results,
            "pageInfo": {"pages": 1},
        }

    def test_request_factory_preserves_overseerr_media_id(self):
        request = OverseerrRequestFactory.from_api(
            {
                "id": 7,
                "media": {"id": 123},
            }
        )

        self.assertEqual(request.media_id, 123)

    def test_clear_media_data_uses_overseerr_clear_data_endpoint(self):
        service = OverseerrService()
        service.http = Mock()

        service.clear_media_data(123)

        service.http.delete.assert_called_once_with(
            f"{Config.OVERSEERR_URL}/api/v1/media/123",
            headers=service.headers,
        )

    def test_connection_uses_authenticated_current_user_endpoint(self):
        service = OverseerrService()
        service.http = Mock()

        service.test_connection()

        service.http.get.assert_called_once_with(
            f"{Config.OVERSEERR_URL}/api/v1/auth/me",
            headers=service.headers,
        )

    def test_forced_request_refresh_finds_request_created_after_cache(self):
        service = OverseerrService()
        service.http = Mock()
        service.http.get.side_effect = [
            self.request_response([]),
            self.request_response(
                [{"id": 7, "media": {"id": 123, "tmdbId": 10386}}]
            ),
        ]

        self.assertEqual(service.get_request_lookup(), {})

        request = service.get_request(10386, refresh=True)

        self.assertEqual(request.id, 7)
        self.assertEqual(service.http.get.call_count, 2)

    def test_successful_overseerr_cleanup_invalidates_request_cache(self):
        service = OverseerrService()
        service.http = Mock()
        service._request_lookup = {10386: Mock()}

        service.delete_request(7)

        self.assertIsNone(service._request_lookup)

        service._request_lookup = {10386: Mock()}
        service.clear_media_data(123)

        self.assertIsNone(service._request_lookup)


if __name__ == "__main__":
    unittest.main()
