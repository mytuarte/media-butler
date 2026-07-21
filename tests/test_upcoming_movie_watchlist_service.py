import unittest
from datetime import date

from models.discovery.discovery_item import DiscoveryItem
from services.upcoming_movie_watchlist_service import UpcomingMovieWatchlistService


class UpcomingMovieWatchlistServiceTests(unittest.TestCase):
    def test_in_theaters_movie_remains_in_watchlist(self):
        service = UpcomingMovieWatchlistService()
        theatrical_movie = DiscoveryItem(
            title="The Odyssey",
            media_type="movie",
            tmdb_id=2,
            release_date=date.today().isoformat(),
        )

        embed = service._embed([theatrical_movie])

        self.assertEqual(embed.description, "⚪ The Odyssey [In Theaters]")

    def test_announced_movie_remains_in_watchlist(self):
        service = UpcomingMovieWatchlistService()
        announced_movie = DiscoveryItem(
            title="Announced Movie",
            media_type="movie",
            tmdb_id=3,
        )

        embed = service._embed([announced_movie])

        self.assertEqual(embed.description, "⚪ Announced Movie [Announced]")


if __name__ == "__main__":
    unittest.main()
