import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from config import Config
from models.notification import MovieNotification
from models.overseerr_request import OverseerrRequest
from routes.webhook_routes import initialize, webhook_routes
from services.discord_service import DiscordService
from services.radarr_service import RadarrService
from services.sonarr_service import SonarrService


class FakeOverseerrService:
    def __init__(self, request=None):
        self.request = request

    def get_request(self, tmdb_id):
        return self.request


class FakeChannel:
    def __init__(self):
        self.messages = []

    async def send(self, **kwargs):
        self.messages.append(kwargs)


class FakeDiscordClient:
    def __init__(self, channels):
        self.channels = channels

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


class CompletionNotificationTests(unittest.TestCase):
    def requester(self, discord_id=297214021784829953, name="Mike"):
        return OverseerrRequest(
            id=1,
            status=2,
            media_status=5,
            requester=name,
            requester_discord_id=discord_id,
            requested_date=None,
            raw={},
        )

    def radarr_service(self, request=None):
        service = RadarrService()
        service.overseerr = FakeOverseerrService(request)
        return service

    def sonarr_service(self, request=None):
        service = SonarrService()
        service.overseerr = FakeOverseerrService(request)
        return service

    def radarr_payload(self, quality):
        movie_file = {} if quality is None else {"quality": quality}
        return {
            "movie": {"title": "The Iron Giant", "year": 1999, "tmdbId": 10386},
            "movieFile": movie_file,
        }

    def sonarr_payload(self, quality):
        episode_file = {} if quality is None else {"quality": quality}
        return {
            "series": {"title": "Shrinking", "year": 2023, "tmdbId": 123},
            "episodes": [
                {"seasonNumber": 2, "episodeNumber": 4, "title": "Made You Look"}
            ],
            "episodeFile": episode_file,
        }

    def test_config_reads_plex_notifications_channel_as_an_integer(self):
        self.assertEqual(Config.DISCORD_PLEX_NOTIFICATIONS_CHANNEL_ID, 8)
        self.assertIsInstance(Config.DISCORD_PLEX_NOTIFICATIONS_CHANNEL_ID, int)

    def test_radarr_normalizes_supported_and_unsupported_quality_shapes(self):
        service = self.radarr_service()
        cases = [
            ("Bluray-2160p", "Bluray-2160p"),
            ({"quality": {"name": "Bluray-1080p"}}, "Bluray-1080p"),
            ({"name": "WEBDL-1080p"}, "WEBDL-1080p"),
            (None, "Unknown"),
            (123, "Unknown"),
            ([], "Unknown"),
            ({}, "Unknown"),
            ({"unexpected": "value"}, "Unknown"),
        ]

        for quality, expected in cases:
            with self.subTest(quality=quality):
                self.assertEqual(
                    service.parse_notification(self.radarr_payload(quality)).quality,
                    expected,
                )

        null_quality_payload = self.radarr_payload("Bluray-2160p")
        null_quality_payload["movieFile"]["quality"] = None
        self.assertEqual(
            service.parse_notification(null_quality_payload).quality, "Unknown"
        )

    def test_sonarr_normalizes_supported_and_unsupported_quality_shapes(self):
        service = self.sonarr_service()
        cases = [
            ("WEBDL-1080p", "WEBDL-1080p"),
            ({"quality": {"name": "Bluray-1080p"}}, "Bluray-1080p"),
            ({"name": "HDTV-720p"}, "HDTV-720p"),
            (None, "Unknown"),
            (123, "Unknown"),
            ([], "Unknown"),
            ({}, "Unknown"),
            ({"unexpected": "value"}, "Unknown"),
        ]

        for quality, expected in cases:
            with self.subTest(quality=quality):
                self.assertEqual(
                    service.parse_notification(self.sonarr_payload(quality)).quality,
                    expected,
                )

        null_quality_payload = self.sonarr_payload("WEBDL-1080p")
        null_quality_payload["episodeFile"]["quality"] = None
        self.assertEqual(
            service.parse_notification(null_quality_payload).quality, "Unknown"
        )

    def test_requester_prefers_mapped_discord_id_with_name_fallback(self):
        mapped_request = self.requester()
        unmapped_request = self.requester(discord_id=None, name="Taylor")

        self.assertEqual(
            self.radarr_service(mapped_request)
            .parse_notification(self.radarr_payload("WEBDL-1080p"))
            .requester,
            297214021784829953,
        )
        self.assertEqual(
            self.sonarr_service(mapped_request)
            .parse_notification(self.sonarr_payload("WEBDL-1080p"))
            .requester,
            297214021784829953,
        )
        self.assertEqual(
            self.radarr_service(unmapped_request)
            .parse_notification(self.radarr_payload("WEBDL-1080p"))
            .requester,
            "Taylor",
        )
        self.assertIsNone(
            self.sonarr_service()
            .parse_notification(self.sonarr_payload("WEBDL-1080p"))
            .requester
        )

    def test_completion_notification_uses_plex_channel_and_mentions_requester(self):
        plex_channel = FakeChannel()
        general_channel = FakeChannel()
        discord_service = DiscordService.__new__(DiscordService)
        discord_service.client = FakeDiscordClient(
            {8: plex_channel, 1: general_channel}
        )
        movie = MovieNotification(
            title="The Iron Giant",
            year=1999,
            requester=297214021784829953,
            quality="Bluray-2160p",
        )

        asyncio.run(discord_service.send_movie_notification(movie))

        self.assertEqual(len(plex_channel.messages), 1)
        self.assertEqual(general_channel.messages, [])
        message = plex_channel.messages[0]
        self.assertEqual(message["content"], "<@297214021784829953>")
        self.assertEqual(message["embed"].fields[0].value, "<@297214021784829953>")

    def test_unavailable_plex_channel_logs_error_without_general_fallback(self):
        general_channel = FakeChannel()
        discord_service = DiscordService.__new__(DiscordService)
        discord_service.client = FakeDiscordClient({1: general_channel})
        movie = MovieNotification("The Iron Giant", 1999, "Mike", "Bluray-2160p")

        with self.assertLogs("media-butler", "ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "Plex notifications channel"):
                asyncio.run(discord_service.send_movie_notification(movie))

        self.assertIn("Plex notifications channel 8 is unavailable", logs.output[0])
        self.assertEqual(general_channel.messages, [])

    def test_completion_webhooks_send_one_notification_for_string_quality(self):
        app = Flask(__name__)
        notifications = []

        class NotificationService:
            async def send_movie_notification(self, notification):
                notifications.append(notification)

        class DiscordService:
            client = SimpleNamespace(loop=object())

        radarr = self.radarr_service(self.requester())
        sonarr = self.sonarr_service(self.requester())
        initialize(NotificationService(), DiscordService(), radarr, sonarr)
        app.register_blueprint(webhook_routes)

        class CompletedFuture:
            def result(self, timeout):
                return None

        def run_notification(coroutine, loop):
            asyncio.run(coroutine)
            return CompletedFuture()

        with patch(
            "routes.webhook_routes.asyncio.run_coroutine_threadsafe", run_notification
        ):
            client = app.test_client()
            radarr_response = client.post(
                "/radarr", json=self.radarr_payload("Bluray-2160p")
            )
            sonarr_response = client.post(
                "/sonarr", json=self.sonarr_payload("WEBDL-1080p")
            )

        self.assertEqual(radarr_response.status_code, 200)
        self.assertEqual(sonarr_response.status_code, 200)
        self.assertEqual(len(notifications), 2)
        self.assertEqual(notifications[0].quality, "Bluray-2160p")
        self.assertEqual(notifications[1].quality, "WEBDL-1080p")


if __name__ == "__main__":
    unittest.main()
