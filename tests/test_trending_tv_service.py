import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from config import Config
from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState
from services.registry import services
from services.trending_tv_service import TrendingTvService


class FakeDiscordService:
    def __init__(self):
        self.sent = []
        self.updated = []
        self.message_exists = True

    async def send_trending_tv(self, embed):
        self.sent.append(embed)
        return SimpleNamespace(id=100 + len(self.sent))

    async def trending_tv_message_exists(self, message_id):
        return self.message_exists

    async def update_trending_tv(self, message_id, embed):
        self.updated.append((message_id, embed))
        return True


class TrendingTvServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.discord = FakeDiscordService()
        self.previous_discord = services.discord
        self.previous_channel_id = Config.DISCORD_TRENDING_TV_CHANNEL_ID
        self.previous_interval = Config.TRENDING_TV_INTERVAL_HOURS
        services.discord = self.discord
        Config.DISCORD_TRENDING_TV_CHANNEL_ID = 456
        Config.TRENDING_TV_INTERVAL_HOURS = 24

    def tearDown(self):
        services.discord = self.previous_discord
        Config.DISCORD_TRENDING_TV_CHANNEL_ID = self.previous_channel_id
        Config.TRENDING_TV_INTERVAL_HOURS = self.previous_interval
        self.temporary_directory.cleanup()

    def create_service(self):
        service = TrendingTvService()
        service.STATE_FILE = Path(self.temporary_directory.name) / "trending_tv.json"
        service.state = service._load_state()
        return service

    def run_cycle(self, service, shows):
        service.discovery.get_watchable_trending_tv = lambda: (shows, len(shows))
        asyncio.run(service.run_cycle())

    def test_statuses_render_for_digital_shows(self):
        service = self.create_service()
        shows = [
            DiscoveryItem("Available", "tv", 1, monitoring_state=MonitoringState.AVAILABLE),
            DiscoveryItem("Requested", "tv", 2, requester="Taylor"),
            DiscoveryItem("Unknown", "tv", 3),
        ]

        self.run_cycle(service, shows)

        self.assertEqual(self.discord.sent[0].title, "📺 Trending TV Shows Right Now")
        self.assertEqual(
            self.discord.sent[0].description,
            "🟢 Available\n🟡 Requested\n⚪ Unknown",
        )

    def test_duplicate_tmdb_ids_are_removed_in_popularity_order(self):
        service = self.create_service()
        self.run_cycle(
            service,
            [
                DiscoveryItem("First", "tv", 1),
                DiscoveryItem("Second", "tv", 2),
                DiscoveryItem("Duplicate", "tv", 1),
            ],
        )

        self.assertEqual(self.discord.sent[0].description, "⚪ First\n⚪ Second")

    def test_dashboard_is_limited_to_twenty_shows(self):
        service = self.create_service()
        shows = [DiscoveryItem(f"Show {number}", "tv", number) for number in range(25)]

        self.run_cycle(service, shows)

        description = self.discord.sent[0].description
        self.assertEqual(len(description.splitlines()), 20)
        self.assertIn("⚪ Show 19", description)
        self.assertNotIn("Show 20", description)


if __name__ == "__main__":
    unittest.main()
