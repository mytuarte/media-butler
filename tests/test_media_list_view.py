import unittest
from datetime import date, timedelta

from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState
from views.media_list_view import MediaListView


class MediaListViewTests(unittest.TestCase):
    def build_movie(
        self,
        monitoring_state: MonitoringState,
        release_date: str | None = None,
        status_detail: str | None = None,
    ):
        return DiscoveryItem(
            title="Movie Title",
            media_type="movie",
            tmdb_id=1,
            monitoring_state=monitoring_state,
            release_date=release_date,
            status_detail=status_detail,
        )

    def test_available_movie_has_no_release_status(self):
        movie = self.build_movie(
            MonitoringState.AVAILABLE,
            status_detail="In Theaters",
        )

        embed = MediaListView.build("Trending Movies", [movie])

        self.assertEqual(embed.description, "🟢 Movie Title")

    def test_requested_announced_movie_shows_release_status(self):
        movie = self.build_movie(
            MonitoringState.COMING_SOON,
            status_detail="Announced",
        )

        embed = MediaListView.build("Trending Movies", [movie])

        self.assertEqual(embed.description, "🟡 Movie Title [Announced]")

    def test_requested_in_theaters_movie_shows_release_status(self):
        movie = self.build_movie(
            MonitoringState.COMING_SOON,
            status_detail="In Theaters",
        )

        embed = MediaListView.build("Trending Movies", [movie])

        self.assertEqual(embed.description, "🟡 Movie Title [In Theaters]")

    def test_not_requested_announced_movie_shows_release_status(self):
        movie = self.build_movie(
            MonitoringState.NOT_ADDED,
            release_date=(date.today() + timedelta(days=1)).isoformat(),
        )

        embed = MediaListView.build("Trending Movies", [movie])

        self.assertEqual(embed.description, "⚪ Movie Title [Announced]")

    def test_upcoming_watchlist_view_keeps_future_release_movies(self):
        movie = self.build_movie(
            MonitoringState.NOT_ADDED,
            release_date="2999-01-01",
        )

        embed = MediaListView.build("🎬 Upcoming Movie Watchlist", [movie])

        self.assertEqual(embed.description, "⚪ Movie Title [Announced]")

    def test_not_requested_in_theaters_movie_shows_release_status(self):
        movie = self.build_movie(
            MonitoringState.NOT_ADDED,
            release_date=date.today().isoformat(),
        )

        embed = MediaListView.build("Trending Movies", [movie])

        self.assertEqual(embed.description, "⚪ Movie Title [In Theaters]")

    def test_footer_uses_user_facing_status_labels(self):
        embed = MediaListView.build("Trending Movies", [])

        self.assertEqual(
            embed.footer.text,
            "🟢 Available · 🟡 Requested · ⚪ Not Requested",
        )
