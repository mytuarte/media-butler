import unittest
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

    def plex_responses(self, movies):
        sections_response = Mock(status_code=200)
        sections_response.json.return_value = {
            "MediaContainer": {
                "Directory": [{"key": "2", "title": "Movies", "type": "movie"}]
            }
        }
        movies_response = Mock(status_code=200)
        movies_response.json.return_value = {
            "MediaContainer": {"totalSize": len(movies), "Metadata": movies}
        }
        return sections_response, movies_response

    def test_plex_movie_lookup_logs_unmatched_results_without_changing_matching(self):
        with patch("services.plex_service.requests.get") as get:
            sections, movies = self.plex_responses([{"Guid": [{"id": "tmdb://999"}]}])
            diagnostic = Mock(status_code=200)
            diagnostic.json.return_value = {"MediaContainer": {"Metadata": []}}
            get.side_effect = [sections, movies, diagnostic]

            with self.assertLogs("media-butler", level="INFO") as logs:
                available = PlexService().movie_is_available(353491, "The Martian")

        self.assertFalse(available)
        self.assertIn("tmdb_id=353491", "\n".join(logs.output))
        self.assertIn("tmdb://999", "\n".join(logs.output))
        self.assertIn(
            "no result contained TMDb GUID tmdb://353491", "\n".join(logs.output)
        )

    def test_plex_movie_lookup_logs_diagnostic_response_details(self):
        item = {
            "title": "The Martian",
            "year": 2015,
            "ratingKey": "42",
            "Guid": [{"id": "plex://movie/42"}, {"id": "tmdb://353491"}],
            "librarySectionID": "2",
            "librarySectionTitle": "Movies",
        }
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = self.plex_responses([item])
            with self.assertLogs("media-butler", level="INFO") as logs:
                available = PlexService().movie_is_available(353491, "The Martian")

        output = "\n".join(logs.output)
        self.assertTrue(available)
        self.assertIn("endpoint=http://plex/library/sections/2/all", output)
        self.assertIn("http_status=200", output)
        self.assertIn("result count: 1", output)
        self.assertIn("title='The Martian' year=2015 ratingKey='42'", output)
        self.assertIn("tmdb://353491", output)
        self.assertIn(
            "library sections searched: [{'key': '2', 'title': 'Movies'}]", output
        )

    def test_plex_movie_lookup_logs_zero_result_response_details(self):
        with patch("services.plex_service.requests.get") as get:
            sections, movies = self.plex_responses([])
            movies.json.return_value = {
                "MediaContainer": {"size": 0, "totalSize": 0, "Metadata": []}
            }
            diagnostic = Mock(status_code=200)
            diagnostic.json.return_value = {"MediaContainer": {"Metadata": []}}
            get.side_effect = [sections, movies, diagnostic]
            with self.assertLogs("media-butler", level="INFO") as logs:
                available = PlexService().movie_is_available(353491, "The Martian")

        self.assertFalse(available)
        self.assertEqual(get.call_count, 3)
        output = "\n".join(logs.output)
        self.assertIn("result count: 0", output)
        self.assertIn("Plex title fallback diagnostic request", output)
        self.assertIn(
            "returned zero results: response_details={'size': 0, 'totalSize': 0}",
            output,
        )

    def test_plex_movie_lookup_matches_tmdb_guid_with_section_inventory_query(self):
        with patch("services.plex_service.requests.get") as get:
            get.side_effect = self.plex_responses([{"Guid": [{"id": "tmdb://353491"}]}])
            available = PlexService().movie_is_available(353491, "The Martian")

        self.assertTrue(available)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].args, ("http://plex/library/sections",))
        self.assertEqual(
            get.call_args_list[0].kwargs,
            {
                "params": {"X-Plex-Token": "plex-token"},
                "headers": {"Accept": "application/json"},
                "timeout": 10,
            },
        )
        self.assertEqual(
            get.call_args_list[1].args, ("http://plex/library/sections/2/all",)
        )
        self.assertEqual(
            get.call_args_list[1].kwargs,
            {
                "params": {
                    "X-Plex-Token": "plex-token",
                    "type": 1,
                    "includeGuids": 1,
                    "X-Plex-Container-Start": 0,
                    "X-Plex-Container-Size": 1000,
                },
                "headers": {"Accept": "application/json"},
                "timeout": 10,
            },
        )

    def test_plex_movie_lookup_checks_each_page_for_an_exact_tmdb_guid(self):
        with patch("services.plex_service.requests.get") as get:
            sections, first_page = self.plex_responses(
                [{"Guid": [{"id": "tmdb://999"}]}]
            )
            first_page.json.return_value["MediaContainer"]["totalSize"] = 2
            second_page = Mock(status_code=200)
            second_page.json.return_value = {
                "MediaContainer": {
                    "totalSize": 2,
                    "Metadata": [{"Guid": [{"id": "tmdb://353491"}]}],
                }
            }
            get.side_effect = [sections, first_page, second_page]

            available = PlexService().movie_is_available(353491, "The Martian")

        self.assertTrue(available)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(
            get.call_args_list[2].kwargs["params"]["X-Plex-Container-Start"], 1
        )


if __name__ == "__main__":
    unittest.main()
