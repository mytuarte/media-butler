import unittest
from unittest.mock import Mock

from models.discovery.discovery_item import DiscoveryItem
from services.discovery.discovery_service import DiscoveryService


class WatchableTrendingMoviesTests(unittest.TestCase):
    def setUp(self):
        self.discovery = DiscoveryService()
        self.discovery.tmdb = Mock()
        self.discovery._enrich = Mock()

    def test_keeps_subscription_rental_and_purchase_provider_movies(self):
        streaming_movie = DiscoveryItem("Streaming", "movie", 1)
        rental_movie = DiscoveryItem("Rental", "movie", 2)
        unavailable_movie = DiscoveryItem("Theater Only", "movie", 3)
        self.discovery.tmdb.get_trending_movies.return_value = [
            streaming_movie,
            rental_movie,
            unavailable_movie,
        ]
        self.discovery.tmdb.movie_has_digital_availability.side_effect = [
            True,
            True,
            False,
        ]

        movies, candidates = self.discovery.get_watchable_trending_movies()

        self.assertEqual(candidates, 3)
        self.assertEqual(movies, [streaming_movie, rental_movie])
        self.discovery.tmdb.get_trending_movies.assert_called_once_with(pages=5)
        self.discovery._enrich.assert_called_once_with(movies)

    def test_excludes_future_and_announced_candidates_without_providers(self):
        future_movie = DiscoveryItem("Future", "movie", 1, release_date="2099-01-01")
        announced_movie = DiscoveryItem("Announced", "movie", 2)
        self.discovery.tmdb.get_trending_movies.return_value = [future_movie, announced_movie]
        self.discovery.tmdb.movie_has_digital_availability.return_value = False

        movies, candidates = self.discovery.get_watchable_trending_movies()

        self.assertEqual(candidates, 2)
        self.assertEqual(movies, [])
        self.discovery._enrich.assert_called_once_with([])


if __name__ == "__main__":
    unittest.main()
