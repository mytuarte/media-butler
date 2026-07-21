import asyncio
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config import Config, _float_config_value
from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState
from models.trending_movies_state import TrendingMoviesState
from services.registry import services
from services.trending_movies_service import TrendingMoviesService


class FakeDiscordService:
    def __init__(self):
        self.sent = []
        self.updated = []
        self.checked = []
        self.message_exists = True
        self.update_result = True

    async def send_trending_movies(self, embed):
        self.sent.append(embed)
        return SimpleNamespace(id=100 + len(self.sent))

    async def trending_movies_message_exists(self, message_id):
        self.checked.append(message_id)
        return self.message_exists

    async def update_trending_movies(self, message_id, embed):
        self.updated.append((message_id, embed))
        return self.update_result


class TrendingMoviesServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "trending_movies.json"
        self.discord = FakeDiscordService()
        self.previous_discord = services.discord
        self.previous_channel_id = Config.DISCORD_TRENDING_MOVIES_CHANNEL_ID
        self.previous_interval = Config.TRENDING_MOVIES_INTERVAL_HOURS
        services.discord = self.discord
        Config.DISCORD_TRENDING_MOVIES_CHANNEL_ID = 123
        Config.TRENDING_MOVIES_INTERVAL_HOURS = 24

    def tearDown(self):
        services.discord = self.previous_discord
        Config.DISCORD_TRENDING_MOVIES_CHANNEL_ID = self.previous_channel_id
        Config.TRENDING_MOVIES_INTERVAL_HOURS = self.previous_interval
        self.temporary_directory.cleanup()

    def create_service(self):
        service = TrendingMoviesService()
        service.STATE_FILE = self.state_file
        service.state = service._load_state()
        return service

    @staticmethod
    def movies(status=MonitoringState.NOT_ADDED):
        return [
            DiscoveryItem(
                title="Example Movie",
                media_type="movie",
                tmdb_id=1,
                release_date=(date.today() - timedelta(days=1)).isoformat(),
                monitoring_state=status,
            )
        ]

    def run_cycle(self, service, movies):
        service.discovery.get_trending_movies = lambda: movies
        asyncio.run(service.run_cycle())

    def test_first_cycle_posts_dashboard_and_persists_state(self):
        service = self.create_service()
        movies = self.movies()

        self.run_cycle(service, movies)

        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(
            self.discord.sent[0].title,
            "🔥 Trending Movies Right Now",
        )
        self.assertEqual(service.state.message_id, 101)
        self.assertEqual(
            json.loads(self.state_file.read_text())["fingerprint"],
            service._fingerprint(movies),
        )

    def test_restart_with_unchanged_content_does_not_post_or_edit(self):
        initial_service = self.create_service()
        movies = self.movies()
        self.run_cycle(initial_service, movies)

        restarted_service = self.create_service()
        self.run_cycle(restarted_service, movies)

        self.assertEqual(self.discord.checked, [101])
        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(self.discord.updated, [])

    def test_changed_content_edits_existing_dashboard_message(self):
        service = self.create_service()
        self.run_cycle(service, self.movies())

        self.run_cycle(service, self.movies(MonitoringState.AVAILABLE))

        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(self.discord.updated[0][0], 101)
        self.assertEqual(
            self.discord.updated[0][1].title,
            "🔥 Trending Movies Right Now",
        )
        self.assertEqual(service.state.message_id, 101)

    def test_changed_ranking_edits_existing_dashboard_message(self):
        service = self.create_service()
        original = self.movies()
        ranked_differently = original + [
            DiscoveryItem(
                "Another Movie",
                "movie",
                2,
                release_date=(date.today() - timedelta(days=1)).isoformat(),
                status_detail="Released",
            )
        ]
        self.run_cycle(service, ranked_differently)

        self.run_cycle(service, list(reversed(ranked_differently)))

        self.assertEqual(self.discord.updated[0][0], 101)

    def test_overseerr_request_changes_visible_status_and_updates_message(self):
        service = self.create_service()
        self.run_cycle(service, self.movies())
        requested_movie = DiscoveryItem(
            title="Example Movie",
            media_type="movie",
            tmdb_id=1,
            release_date=(date.today() - timedelta(days=1)).isoformat(),
            requester="Example User",
            status_detail="Released",
        )

        self.run_cycle(service, [requested_movie])

        self.assertEqual(self.discord.updated[0][1].description, "🟡 Example Movie")

    def test_missing_dashboard_message_is_replaced(self):
        service = self.create_service()
        self.run_cycle(service, self.movies())
        self.discord.message_exists = False
        self.discord.update_result = False

        self.run_cycle(service, self.movies())

        self.assertEqual(len(self.discord.sent), 2)
        self.assertEqual(service.state.message_id, 102)

    def test_failed_edit_keeps_previous_state_for_retry(self):
        service = self.create_service()
        original_movies = self.movies()
        self.run_cycle(service, original_movies)
        original_fingerprint = service.state.fingerprint
        self.discord.update_result = None

        self.run_cycle(service, self.movies(MonitoringState.AVAILABLE))

        self.assertEqual(service.state.fingerprint, original_fingerprint)
        self.assertEqual(len(self.discord.sent), 1)

    def test_non_visible_fields_do_not_change_fingerprint(self):
        original = self.movies()[0]
        changed = DiscoveryItem(
            title=original.title,
            media_type=original.media_type,
            tmdb_id=original.tmdb_id,
            release_date=original.release_date,
            poster_url="https://example.test/poster.jpg",
            overview="Changed overview",
        )

        self.assertEqual(
            TrendingMoviesService._fingerprint([original]),
            TrendingMoviesService._fingerprint([changed]),
        )

    def test_trending_movie_not_in_plex_or_requested_appears_in_dashboard(self):
        service = self.create_service()

        self.run_cycle(service, self.movies())

        self.assertEqual(self.discord.sent[0].description, "⚪ Example Movie")

    def test_requested_movie_not_downloaded_appears_in_dashboard(self):
        service = self.create_service()
        requested_movie = DiscoveryItem(
            title="Requested Movie",
            media_type="movie",
            tmdb_id=2,
            release_date=date.today().isoformat(),
            monitoring_state=MonitoringState.COMING_SOON,
            status_detail="Released",
        )

        self.run_cycle(service, [requested_movie])

        self.assertEqual(self.discord.sent[0].description, "🟡 Requested Movie")

    def test_plex_owned_movie_appears_in_dashboard(self):
        service = self.create_service()
        plex_movie = DiscoveryItem(
            title="Plex Movie",
            media_type="movie",
            tmdb_id=2,
            release_date=(date.today() - timedelta(days=1)).isoformat(),
            monitoring_state=MonitoringState.AVAILABLE,
        )

        self.run_cycle(service, [plex_movie])

        self.assertEqual(self.discord.sent[0].description, "🟢 Plex Movie")

    def test_future_release_movie_is_excluded_from_dashboard(self):
        service = self.create_service()
        future_movie = DiscoveryItem(
            title="Future Movie",
            media_type="movie",
            tmdb_id=2,
            release_date=(date.today() + timedelta(days=1)).isoformat(),
        )

        self.run_cycle(service, self.movies() + [future_movie])

        self.assertEqual(self.discord.sent[0].description, "⚪ Example Movie")

    def test_announced_movie_is_excluded_from_dashboard(self):
        service = self.create_service()
        announced_movie = DiscoveryItem(
            title="Announced Movie",
            media_type="movie",
            tmdb_id=2,
        )

        self.run_cycle(service, self.movies() + [announced_movie])

        self.assertEqual(self.discord.sent[0].description, "⚪ Example Movie")

    def test_movie_with_invalid_release_date_is_excluded_from_dashboard(self):
        service = self.create_service()
        invalid_release_date_movie = DiscoveryItem(
            title="Unknown Release",
            media_type="movie",
            tmdb_id=2,
            release_date="not-a-date",
        )

        self.run_cycle(service, self.movies() + [invalid_release_date_movie])

        self.assertEqual(self.discord.sent[0].description, "⚪ Example Movie")

    def test_in_theaters_movie_appears_in_dashboard(self):
        service = self.create_service()
        theatrical_movie = DiscoveryItem(
            title="The Odyssey",
            media_type="movie",
            tmdb_id=2,
            release_date=date.today().isoformat(),
        )

        self.run_cycle(service, self.movies() + [theatrical_movie])

        self.assertEqual(
            self.discord.sent[0].description,
            "⚪ Example Movie\n⚪ The Odyssey",
        )

    def test_upcoming_movie_does_not_change_dashboard_fingerprint(self):
        service = self.create_service()
        released_movies = self.movies()
        future_movie = DiscoveryItem(
            title="Future Movie",
            media_type="movie",
            tmdb_id=2,
            release_date=(date.today() + timedelta(days=1)).isoformat(),
        )
        self.run_cycle(service, released_movies)

        self.run_cycle(service, released_movies + [future_movie])

        self.assertEqual(self.discord.updated, [])

    def test_start_is_disabled_without_a_trending_movies_channel(self):
        service = self.create_service()
        Config.DISCORD_TRENDING_MOVIES_CHANNEL_ID = None

        service.start()

        self.assertFalse(service.running)
        self.assertIsNone(service._task)

    def test_decimal_interval_config_value_is_supported(self):
        with patch.dict(
            "os.environ",
            {"TRENDING_MOVIES_INTERVAL_HOURS": "0.05"},
        ):
            interval = _float_config_value(
                "TRENDING_MOVIES_INTERVAL_HOURS",
                "24",
            )

        self.assertEqual(interval, 0.05)

    def test_start_is_disabled_with_a_non_positive_interval(self):
        service = self.create_service()
        Config.TRENDING_MOVIES_INTERVAL_HOURS = 0

        service.start()

        self.assertFalse(service.running)
        self.assertIsNone(service._task)

    def test_state_model_rejects_invalid_message_id(self):
        with self.assertRaises(ValueError):
            TrendingMoviesState.from_dict(
                {
                    "fingerprint": "abc",
                    "message_id": "101",
                    "updated_at": "2026-07-21T12:00:00+00:00",
                }
            )
