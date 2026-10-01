import unittest
from unittest.mock import Mock, patch

from services.discovery.tmdb_service import TmdbService


class TmdbDiscoveryDetailsTests(unittest.TestCase):
    @patch("services.discovery.tmdb_service.requests.get")
    def test_details_include_summary_rating_and_streaming_only(self, get):
        response = Mock()
        response.json.return_value = {
            "title": "Example Movie",
            "id": 123,
            "overview": "A useful synopsis.",
            "release_date": "2026-09-29",
            "poster_path": "/poster.jpg",
            "vote_average": 7.4,
            "vote_count": 1234,
            "watch/providers": {
                "results": {
                    "US": {
                        "flatrate": [{"provider_name": "Netflix"}],
                        "free": [{"provider_name": "Tubi"}],
                        "ads": [{"provider_name": "Hulu"}],
                        "rent": [{"provider_name": "Apple TV"}],
                        "buy": [{"provider_name": "Amazon Video"}],
                    }
                }
            },
        }
        get.return_value = response

        details = TmdbService().get_details("movie", 123)

        self.assertEqual(details.title, "Example Movie")
        self.assertEqual(details.overview, "A useful synopsis.")
        self.assertEqual(details.vote_average, 7.4)
        self.assertEqual(details.vote_count, 1234)
        self.assertEqual(details.streaming_providers, ("Netflix", "Tubi", "Hulu"))
        self.assertNotIn("Apple TV", details.streaming_providers)
        self.assertNotIn("Amazon Video", details.streaming_providers)
        self.assertEqual(
            get.call_args.kwargs["params"]["append_to_response"],
            "watch/providers",
        )

    @patch("services.discovery.tmdb_service.requests.get")
    def test_tv_details_use_show_fields(self, get):
        response = Mock()
        response.json.return_value = {
            "name": "Example Show",
            "first_air_date": "2026-01-01",
            "vote_average": 8,
            "vote_count": 10,
            "watch/providers": {"results": {"US": {}}},
        }
        get.return_value = response

        details = TmdbService().get_details("tv", 456)

        self.assertEqual(details.title, "Example Show")
        self.assertEqual(details.media_type, "tv")
        self.assertEqual(details.release_date, "2026-01-01")
        self.assertEqual(details.streaming_providers, ())

    def test_details_reject_invalid_inputs(self):
        service = TmdbService()

        with self.assertRaises(ValueError):
            service.get_details("music", 123)

        with self.assertRaises(ValueError):
            service.get_details("movie", 0)


if __name__ == "__main__":
    unittest.main()
