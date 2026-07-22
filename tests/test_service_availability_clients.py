import unittest

import requests
from unittest.mock import Mock, patch

from config import Config
from services.plex_service import PlexService
from services.radarr_service import RadarrService
from services.sabnzbd_client import SabnzbdClient
from services.sonarr_service import SonarrService


class ServiceAvailabilityClientTests(unittest.TestCase):
    def setUp(self):
        self.previous_values = {
            "PLEX_TOKEN": Config.PLEX_TOKEN,
            "PLEX_URL": Config.PLEX_URL,
            "RADARR_API_KEY": Config.RADARR_API_KEY,
            "RADARR_URL": Config.RADARR_URL,
            "SABNZBD_API_KEY": Config.SABNZBD_API_KEY,
            "SABNZBD_URL": Config.SABNZBD_URL,
            "SONARR_API_KEY": Config.SONARR_API_KEY,
            "SONARR_URL": Config.SONARR_URL,
        }
        Config.PLEX_TOKEN = "plex-token"
        Config.PLEX_URL = "http://plex"
        Config.RADARR_API_KEY = "radarr-key"
        Config.RADARR_URL = "http://radarr"
        Config.SABNZBD_API_KEY = "sabnzbd-key"
        Config.SABNZBD_URL = "http://sabnzbd"
        Config.SONARR_API_KEY = "sonarr-key"
        Config.SONARR_URL = "http://sonarr"

    def tearDown(self):
        for name, value in self.previous_values.items():
            setattr(Config, name, value)

    def assert_probe(self, service, request_path, expected_kwargs):
        with patch(request_path) as get:
            response = get.return_value

            service.test_connection()

        url = expected_kwargs.pop("url")
        get.assert_called_once_with(url, **expected_kwargs)
        response.raise_for_status.assert_called_once_with()

    def test_radarr_probe_uses_system_status_endpoint(self):
        self.assert_probe(
            RadarrService(),
            "services.radarr_service.requests.get",
            {
                "url": "http://radarr/api/v3/system/status",
                "headers": {"X-Api-Key": "radarr-key"},
                "timeout": 10,
            },
        )

    def test_sonarr_probe_uses_system_status_endpoint(self):
        self.assert_probe(
            SonarrService(),
            "services.sonarr_service.requests.get",
            {
                "url": "http://sonarr/api/v3/system/status",
                "headers": {"X-Api-Key": "sonarr-key"},
                "timeout": 10,
            },
        )

    def test_sabnzbd_probe_uses_version_endpoint(self):
        self.assert_probe(
            SabnzbdClient(),
            "services.sabnzbd_client.requests.get",
            {
                "url": "http://sabnzbd/api",
                "params": {
                    "mode": "version",
                    "apikey": "sabnzbd-key",
                    "output": "json",
                },
                "timeout": 10,
            },
        )

    def test_plex_probe_uses_authenticated_identity_endpoint(self):
        self.assert_probe(
            PlexService(),
            "services.plex_service.requests.get",
            {
                "url": "http://plex/identity",
                "params": {"X-Plex-Token": "plex-token"},
                "timeout": 10,
            },
        )

    def test_sabnzbd_history_uses_history_endpoint(self):
        with patch("services.sabnzbd_client.requests.get") as get:
            response = get.return_value
            response.json.return_value = {"history": {"slots": []}}

            self.assertEqual(SabnzbdClient().get_history(), {"history": {"slots": []}})

        get.assert_called_once_with(
            "http://sabnzbd/api",
            params={"mode": "history", "apikey": "sabnzbd-key", "output": "json"},
            timeout=10,
        )
        response.raise_for_status.assert_called_once_with()

    def plex_response(self, payload):
        response = Mock(status_code=200)
        response.json.return_value = payload
        return response

    def plex_responses(self, movies, sections=None):
        sections = sections or [{"key": "2", "title": "Movies", "type": "movie"}]
        return (
            self.plex_response({"MediaContainer": {"Directory": sections}}),
            self.plex_response(
                {"MediaContainer": {"totalSize": len(movies), "Metadata": movies}}
            ),
        )

    def test_plex_movie_lookup_matches_exact_tmdb_guid(self):
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = self.plex_responses(
                [{"Guid": [{"id": "plex://movie/42"}, {"id": "tmdb://353491"}]}]
            )

            available = PlexService().movie_is_available(353491, "The Martian")

        self.assertTrue(available)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].args, ("http://plex/library/sections",))
        self.assertEqual(
            get.call_args_list[1].args, ("http://plex/library/sections/2/all",)
        )
        self.assertEqual(get.call_args_list[1].kwargs["params"]["includeGuids"], 1)

    def test_plex_movie_lookup_rejects_different_or_missing_tmdb_guid(self):
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = self.plex_responses(
                [
                    {"Guid": [{"id": "tmdb://999"}]},
                    {"Guid": [{"id": "plex://movie/43"}]},
                ]
            )

            service = PlexService()
            self.assertFalse(service.movie_is_available(353491, "The Martian"))
            self.assertFalse(service.movie_is_available(9999, "Other Movie"))

        self.assertEqual(get.call_count, 2)

    def test_plex_movie_lookup_does_not_use_title_as_availability_fallback(self):
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = self.plex_responses(
                [{"title": "The Martian", "Guid": [{"id": "tmdb://999"}]}]
            )

            available = PlexService().movie_is_available(353491, "The Martian")

        self.assertFalse(available)
        self.assertEqual(get.call_count, 2)

    def test_plex_movie_inventory_is_reused_within_cache_lifetime(self):
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = self.plex_responses([{"Guid": [{"id": "tmdb://353491"}]}])
            service = PlexService()

            self.assertTrue(service.movie_is_available(353491, "The Martian"))
            self.assertFalse(service.movie_is_available(999, "Unrelated"))

        self.assertEqual(get.call_count, 2)

    def test_plex_movie_inventory_refreshes_after_cache_expiration(self):
        with patch("services.plex_service.requests.get") as get, patch(
            "services.plex_service.time.monotonic", side_effect=[100, 401, 401]
        ):
            get.side_effect = [
                *self.plex_responses([{"Guid": [{"id": "tmdb://353491"}]}]),
                *self.plex_responses([{"Guid": [{"id": "tmdb://999"}]}]),
            ]
            service = PlexService()

            self.assertTrue(service.movie_is_available(353491, "The Martian"))
            self.assertTrue(service.movie_is_available(999, "Other"))

        self.assertEqual(get.call_count, 4)

    def test_failed_refresh_does_not_overwrite_valid_movie_inventory(self):
        with patch("services.plex_service.requests.get") as get, patch(
            "services.plex_service.time.monotonic", side_effect=[100, 401]
        ):
            sections, movies = self.plex_responses(
                [{"Guid": [{"id": "tmdb://353491"}]}]
            )
            failure = requests.ConnectionError("connection refused")
            get.side_effect = [sections, movies, failure]
            service = PlexService()

            self.assertTrue(service.movie_is_available(353491, "The Martian"))
            with self.assertRaises(requests.ConnectionError):
                service.movie_is_available(999, "Other")

        self.assertIn(353491, service._movie_inventory)
        self.assertEqual(service._movie_inventory_refreshed_at, 100)

    def test_plex_movie_inventory_pages_multiple_movie_sections(self):
        sections = [
            {"key": "2", "title": "Movies", "type": "movie"},
            {"key": "3", "title": "More Movies", "type": "movie"},
            {"key": "4", "title": "Shows", "type": "show"},
        ]
        first_page = self.plex_response(
            {
                "MediaContainer": {
                    "totalSize": 2,
                    "Metadata": [{"Guid": [{"id": "tmdb://1"}]}],
                }
            }
        )
        second_page = self.plex_response(
            {
                "MediaContainer": {
                    "totalSize": 2,
                    "Metadata": [{"Guid": [{"id": "tmdb://2"}]}],
                }
            }
        )
        other_section = self.plex_response(
            {
                "MediaContainer": {
                    "totalSize": 1,
                    "Metadata": [{"Guid": [{"id": "tmdb://353491"}]}],
                }
            }
        )
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = [
                self.plex_response({"MediaContainer": {"Directory": sections}}),
                first_page,
                second_page,
                other_section,
            ]
            available = PlexService().movie_is_available(353491, "The Martian")

        self.assertTrue(available)
        self.assertEqual(get.call_count, 4)
        self.assertEqual(
            get.call_args_list[2].kwargs["params"]["X-Plex-Container-Start"], 1
        )
        self.assertEqual(
            get.call_args_list[3].args, ("http://plex/library/sections/3/all",)
        )

    def test_plex_movie_lookup_logs_refresh_and_match_concisely(self):
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = self.plex_responses([{"Guid": [{"id": "tmdb://353491"}]}])
            with self.assertLogs("media-butler", level="INFO") as logs:
                PlexService().movie_is_available(353491, "The Martian")

        output = "\n".join(logs.output)
        self.assertIn("inventory refresh started", output)
        self.assertIn("movie_sections=1 movies_indexed=1", output)
        self.assertIn("availability match found: tmdb_id=353491", output)
        self.assertNotIn("Plex movie lookup result:", output)

    def test_plex_availability_miss_is_debug(self):
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = self.plex_responses([])
            with self.assertLogs("media-butler", level="DEBUG") as logs:
                self.assertFalse(
                    PlexService().movie_is_available(353491, "The Martian")
                )

        self.assertIn(
            "DEBUG:media-butler:Plex availability not found", "\n".join(logs.output)
        )

    def test_plex_refresh_failure_remains_warning(self):
        with patch(
            "services.plex_service.requests.get",
            side_effect=requests.ConnectionError("offline"),
        ):
            with self.assertLogs("media-butler", level="WARNING") as logs:
                with self.assertRaises(requests.ConnectionError):
                    PlexService().movie_is_available(353491, "The Martian")

        self.assertIn(
            "WARNING:media-butler:Plex movie inventory refresh failed",
            "\n".join(logs.output),
        )


if __name__ == "__main__":
    unittest.main()
