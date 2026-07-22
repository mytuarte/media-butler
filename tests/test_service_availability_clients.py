import unittest
from unittest.mock import patch

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

    def test_plex_movie_lookup_matches_tmdb_guid(self):
        with patch("services.plex_service.requests.get") as get:
            response = get.return_value
            response.json.return_value = {
                "MediaContainer": {"Metadata": [{"Guid": [{"id": "tmdb://353491"}]}]}
            }

            available = PlexService().movie_is_available(353491, "The Martian")

        self.assertTrue(available)
        get.assert_called_once_with(
            "http://plex/library/all",
            params={
                "X-Plex-Token": "plex-token",
                "type": 1,
                "guid": "tmdb://353491",
                "includeGuids": 1,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
