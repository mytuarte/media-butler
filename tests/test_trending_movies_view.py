import unittest

from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState
from views.trending_movies_view import TrendingMoviesView


class TrendingMoviesViewTests(unittest.TestCase):
    def test_displays_popularity_order_and_availability_states(self):
        movies = [
            DiscoveryItem("Requested", "movie", 1, monitoring_state=MonitoringState.COMING_SOON),
            DiscoveryItem("Available", "movie", 2, monitoring_state=MonitoringState.AVAILABLE),
            DiscoveryItem("Unknown", "movie", 3, release_date="2026-01-01"),
        ]

        embed = TrendingMoviesView.build(movies)

        self.assertEqual(embed.title, "🔥 Trending Movies Right Now")
        self.assertEqual(embed.description, "🟡 Requested\n🟢 Available\n⚪ Unknown")
        self.assertNotIn("Announced", embed.description)
        self.assertNotIn("In Theaters", embed.description)
        self.assertEqual(embed.footer.text, TrendingMoviesView.FOOTER_LEGEND)

    def test_overseerr_request_is_requested_when_not_in_library(self):
        movie = DiscoveryItem("Requested", "movie", 1, requester="Taylor")

        self.assertEqual(TrendingMoviesView.status(movie), "requested")
