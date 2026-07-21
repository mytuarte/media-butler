from datetime import date, timedelta
import unittest
from unittest.mock import Mock

from models.discovery.discovery_item import DiscoveryItem
from services.discovery.discovery_service import DiscoveryService


class WatchableTrendingTvTests(unittest.TestCase):
    def setUp(self):
        self.discovery = DiscoveryService()
        self.discovery.tmdb = Mock()
        self.discovery._enrich = Mock()

    def test_includes_digitally_available_already_airing_show(self):
        show = DiscoveryItem(
            "Streaming Show",
            "tv",
            1,
            release_date=(date.today() - timedelta(days=1)).isoformat(),
        )
        self.discovery.tmdb.get_trending_tv.return_value = [show]
        self.discovery.tmdb.tv_has_digital_availability.return_value = True

        shows, candidate_count = self.discovery.get_watchable_trending_tv()

        self.assertEqual(shows, [show])
        self.assertEqual(candidate_count, 1)
        self.discovery.tmdb.get_trending_tv.assert_called_once_with(pages=5)

    def test_excludes_show_without_digital_provider(self):
        show = DiscoveryItem("No Provider", "tv", 1, release_date="2020-01-01")
        self.discovery.tmdb.get_trending_tv.return_value = [show]
        self.discovery.tmdb.tv_has_digital_availability.return_value = False

        shows, _ = self.discovery.get_watchable_trending_tv()

        self.assertEqual(shows, [])

    def test_excludes_future_and_announced_shows_before_provider_lookup(self):
        future_show = DiscoveryItem(
            "Future Show",
            "tv",
            1,
            release_date=(date.today() + timedelta(days=1)).isoformat(),
        )
        announced_show = DiscoveryItem("Announced Show", "tv", 2)
        self.discovery.tmdb.get_trending_tv.return_value = [future_show, announced_show]

        shows, _ = self.discovery.get_watchable_trending_tv()

        self.assertEqual(shows, [])
        self.discovery.tmdb.tv_has_digital_availability.assert_not_called()


if __name__ == "__main__":
    unittest.main()
