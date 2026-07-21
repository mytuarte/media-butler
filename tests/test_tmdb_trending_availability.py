import unittest
from unittest.mock import Mock, patch

from services.discovery.tmdb_service import TmdbService


class TmdbTrendingAvailabilityTests(unittest.TestCase):
    @patch("services.discovery.tmdb_service.requests.get")
    def test_trending_movies_fetches_each_requested_page(self, get):
        first_page = Mock()
        first_page.json.return_value = {
            "results": [{"title": "First", "id": 1, "poster_path": None}]
        }
        second_page = Mock()
        second_page.json.return_value = {
            "results": [{"title": "Second", "id": 2, "poster_path": None}]
        }
        get.side_effect = [first_page, second_page]

        movies = TmdbService().get_trending_movies(pages=2)

        self.assertEqual([movie.title for movie in movies], ["First", "Second"])
        self.assertEqual(get.call_args_list[0].kwargs["params"]["page"], 1)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["page"], 2)

    @patch("services.discovery.tmdb_service.requests.get")
    def test_provider_filter_accepts_streaming_rental_and_purchase(self, get):
        response = Mock()
        get.return_value = response
        service = TmdbService()

        for provider_type in ("flatrate", "rent", "buy"):
            response.json.return_value = {"results": {"US": {provider_type: [{}]}}}

            self.assertTrue(service.movie_has_digital_availability(1))

    @patch("services.discovery.tmdb_service.requests.get")
    def test_provider_filter_excludes_theater_only_and_missing_regions(self, get):
        response = Mock()
        get.return_value = response
        service = TmdbService()

        response.json.return_value = {"results": {"US": {"link": "theaters only"}}}
        self.assertFalse(service.movie_has_digital_availability(1))

        response.json.return_value = {"results": {}}
        self.assertFalse(service.movie_has_digital_availability(2))

    @patch("services.discovery.tmdb_service.requests.get")
    def test_tv_provider_filter_accepts_digital_options_only(self, get):
        response = Mock()
        get.return_value = response
        service = TmdbService()

        for provider_type in ("flatrate", "rent", "buy"):
            response.json.return_value = {"results": {"US": {provider_type: [{}]}}}
            self.assertTrue(service.tv_has_digital_availability(1))

        response.json.return_value = {"results": {"US": {"link": "no providers"}}}
        self.assertFalse(service.tv_has_digital_availability(1))


if __name__ == "__main__":
    unittest.main()
