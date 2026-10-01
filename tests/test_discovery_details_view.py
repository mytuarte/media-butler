import unittest

from models.discovery.discovery_details import DiscoveryDetails
from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState
from views.discovery_details_view import DiscoveryDetailsView


class DiscoveryDetailsViewTests(unittest.TestCase):
    def test_selection_labels_keep_request_and_release_state_visible(self):
        items = [
            DiscoveryItem(
                "Requested Movie",
                "movie",
                1,
                release_date="2999-01-01",
                monitoring_state=MonitoringState.COMING_SOON,
                status_detail="Announced",
            ),
            DiscoveryItem(
                "Available Movie",
                "movie",
                2,
                monitoring_state=MonitoringState.AVAILABLE,
            ),
        ]

        view = DiscoveryDetailsView.from_items(items, "trending_movies")

        self.assertIsNotNone(view)
        options = view.children[0].options
        self.assertEqual(options[0].label, "🟡 Requested Movie [Announced]")
        self.assertEqual(options[1].label, "🟢 Available Movie")
        self.assertEqual(options[0].value, "movie:1")

    def test_details_embed_shows_streaming_rating_and_summary(self):
        embed = DiscoveryDetailsView.build(
            DiscoveryDetails(
                title="Example Movie",
                media_type="movie",
                tmdb_id=123,
                overview="A synopsis.",
                vote_average=7.4,
                vote_count=1234,
                streaming_providers=("Netflix", "Tubi"),
            )
        )

        rendered = str(embed.to_dict())
        self.assertIn("A synopsis.", rendered)
        self.assertIn("7.4/10 (1,234 votes)", rendered)
        self.assertIn("Netflix", rendered)
        self.assertIn("Tubi", rendered)
        self.assertNotIn("Rent", rendered)
        self.assertNotIn("Buy", rendered)

    def test_missing_streaming_is_explicit(self):
        embed = DiscoveryDetailsView.build(
            DiscoveryDetails(
                title="Theater Only",
                media_type="movie",
                tmdb_id=123,
            )
        )

        self.assertIn(
            "No subscription streaming service listed in the US.",
            str(embed.to_dict()),
        )


if __name__ == "__main__":
    unittest.main()
