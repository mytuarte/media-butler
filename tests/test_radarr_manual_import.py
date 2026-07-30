import ntpath
import os
import sys
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from config import Config
from services.radarr_service import RadarrService, RadarrServiceError


class RadarrManualImportTests(unittest.TestCase):
    def setUp(self):
        Config.RADARR_URL = "http://radarr"
        Config.RADARR_API_KEY = "radarr-key"
        self.service = RadarrService()
        self.quality = {
            "quality": {"id": 7, "name": "Bluray-1080p"},
            "revision": {"version": 1, "real": 0, "isRepack": False},
        }
        self.languages = [{"id": 1, "name": "English"}]
        self.candidate = {
            "path": "/downloads/movie/Movie.mkv",
            "folderName": "movie",
            "movie": {"id": 42, "title": "Movie"},
            "releaseGroup": "GROUP",
            "quality": self.quality,
            "languages": self.languages,
            "indexerFlags": 2,
            "downloadId": "download-123",
        }

    @patch("services.radarr_service.requests.get")
    def test_get_movie_by_id_requires_exact_integer_response_identity(self, get):
        get.return_value.status_code = 200
        for response_id in (True, False, 42.0, "42", 0, -42, 41, None):
            with self.subTest(response_id=response_id):
                get.return_value.json.return_value = {"id": response_id}
                with self.assertRaisesRegex(RadarrServiceError, "response ID"):
                    self.service.get_movie_by_id(42)

    def test_movie_file_snapshot_requires_exact_nested_integer_identity(self):
        base = {
            "id": 42,
            "movieFileId": 70,
            "movieFile": {
                "id": 70, "movieId": 42, "path": "/movies/Movie.mkv",
                "size": 100, "quality": self.quality,
            },
        }
        with patch.object(self.service, "get_movie_by_id", return_value=base):
            snapshot = self.service.get_movie_file_snapshot(42)
            self.assertEqual(snapshot["movie_file_id"], 70)

        malformed = (True, False, 70.0, "70", 0, -70, 71, None)
        for field in ("id", "movieId"):
            expected = 70 if field == "id" else 42
            for value in malformed:
                if value == expected and type(value) is int:
                    continue
                with self.subTest(field=field, value=value):
                    movie = {
                        **base,
                        "movieFile": {**base["movieFile"], field: value},
                    }
                    with patch.object(self.service, "get_movie_by_id", return_value=movie):
                        with self.assertRaisesRegex(RadarrServiceError, "identified"):
                            self.service.get_movie_file_snapshot(42)

    @patch("services.radarr_service.requests.get")
    def test_get_manual_import_candidates_uses_exact_request(self, get):
        candidates = [self.candidate]
        get.return_value.json.return_value = candidates

        result = self.service.get_manual_import_candidates("download-123", 42)

        self.assertIs(result, candidates)
        get.assert_called_once_with(
            "http://radarr/api/v3/manualimport",
            headers={"X-Api-Key": "radarr-key"},
            params={
                "downloadId": "download-123",
                "movieId": 42,
                "filterExistingFiles": True,
            },
            timeout=10,
        )
        get.return_value.raise_for_status.assert_called_once_with()

    @patch("services.radarr_service.requests.get")
    def test_get_manual_import_candidates_rejects_malformed_responses(self, get):
        for payload in ({"path": "/movie.mkv"}, [self.candidate, "bad"], None):
            with self.subTest(payload=payload):
                get.return_value.json.return_value = payload
                with self.assertRaisesRegex(RadarrServiceError, "list of objects"):
                    self.service.get_manual_import_candidates("download-123", 42)

        get.return_value.json.side_effect = ValueError("not json")
        with self.assertRaisesRegex(RadarrServiceError, "JSON list of objects"):
            self.service.get_manual_import_candidates("download-123", 42)

    @patch("services.radarr_service.requests.get")
    def test_get_manual_import_candidates_rejects_invalid_inputs_before_get(self, get):
        invalid_inputs = [
            ("", 42),
            ("   ", 42),
            (None, 42),
            (123, 42),
            ("download-123", 0),
            ("download-123", -1),
            ("download-123", True),
            ("download-123", False),
            ("download-123", "42"),
            ("download-123", 42.0),
        ]
        for download_id, movie_id in invalid_inputs:
            with self.subTest(download_id=download_id, movie_id=movie_id):
                with self.assertRaises(RadarrServiceError):
                    self.service.get_manual_import_candidates(download_id, movie_id)
        get.assert_not_called()

    @patch("services.radarr_service.requests.post")
    def test_submit_manual_import_candidate_uses_exact_payload(self, post):
        command = {"id": 987, "name": "ManualImport", "status": "queued"}
        post.return_value.json.return_value = command

        result = self.service.submit_manual_import_candidate(
            self.candidate, "download-123", 42
        )

        self.assertIs(result, command)
        payload = {
            "name": "ManualImport",
            "files": [
                {
                    "path": "/downloads/movie/Movie.mkv",
                    "folderName": "movie",
                    "movieId": 42,
                    "releaseGroup": "GROUP",
                    "quality": self.quality,
                    "languages": self.languages,
                    "indexerFlags": 2,
                    "downloadId": "download-123",
                }
            ],
            "importMode": "auto",
        }
        post.assert_called_once_with(
            "http://radarr/api/v3/command",
            headers={"X-Api-Key": "radarr-key"},
            json=payload,
            timeout=15,
        )
        self.assertIs(payload["files"][0]["quality"], self.quality)
        self.assertIs(payload["files"][0]["languages"], self.languages)
        post.return_value.raise_for_status.assert_called_once_with()

    @patch("services.radarr_service.requests.post")
    def test_posix_absolute_path_is_accepted_independently_of_host_os(self, post):
        self.assertFalse(ntpath.isabs(self.candidate["path"]))
        post.return_value.json.return_value = {"id": 987}

        self.service.submit_manual_import_candidate(
            self.candidate, "download-123", 42
        )

        post.assert_called_once()

    @patch("services.radarr_service.requests.delete")
    @patch("services.radarr_service.requests.post")
    def test_submit_never_deletes(self, post, delete):
        post.return_value.json.return_value = {"id": 987}
        self.service.submit_manual_import_candidate(self.candidate, "download-123", 42)
        delete.assert_not_called()

    @patch("services.radarr_service.requests.post")
    def test_invalid_candidate_is_rejected_before_post(self, post):
        invalid_cases = [
            ({**self.candidate, "movie": {"id": 41}}, "download-123", 42),
            ({**self.candidate, "downloadId": "other"}, "download-123", 42),
            ({**self.candidate, "path": ""}, "download-123", 42),
            ({**self.candidate, "path": "relative/Movie.mkv"}, "download-123", 42),
            (self.candidate, "", 42),
            (self.candidate, "download-123", 0),
        ]
        for candidate, download_id, movie_id in invalid_cases:
            with self.subTest(
                candidate=candidate, download_id=download_id, movie_id=movie_id
            ):
                with self.assertRaises(RadarrServiceError):
                    self.service.submit_manual_import_candidate(
                        candidate, download_id, movie_id
                    )
        post.assert_not_called()

    @patch("services.radarr_service.requests.post")
    def test_submit_propagates_http_errors_and_rejects_malformed_response(self, post):
        post.return_value.raise_for_status.side_effect = requests.HTTPError("bad")
        with self.assertRaises(requests.HTTPError):
            self.service.submit_manual_import_candidate(
                self.candidate, "download-123", 42
            )

        post.return_value.raise_for_status.side_effect = None
        post.return_value.json.return_value = []
        with self.assertRaisesRegex(RadarrServiceError, "JSON object"):
            self.service.submit_manual_import_candidate(
                self.candidate, "download-123", 42
            )

        post.return_value.json.side_effect = ValueError("not json")
        with self.assertRaisesRegex(RadarrServiceError, "object with an ID"):
            self.service.submit_manual_import_candidate(
                self.candidate, "download-123", 42
            )

    @patch("services.radarr_service.requests.post")
    def test_submit_rejects_invalid_command_response_ids(self, post):
        for payload in (
            {},
            {"status": "queued"},
            {"id": "987"},
            {"id": True},
            {"id": False},
            {"id": 0},
            {"id": -1},
            {"id": 987.0},
        ):
            with self.subTest(payload=payload):
                post.return_value.json.return_value = payload
                with self.assertRaisesRegex(
                    RadarrServiceError, "positive integer ID"
                ):
                    self.service.submit_manual_import_candidate(
                        self.candidate, "download-123", 42
                    )

    @patch("services.radarr_service.requests.get")
    def test_get_command_status_uses_exact_returned_id(self, get):
        status = {"id": 987, "status": "completed"}
        get.return_value.json.return_value = status

        result = self.service.get_command_status(987)

        self.assertIs(result, status)
        get.assert_called_once_with(
            "http://radarr/api/v3/command/987",
            headers={"X-Api-Key": "radarr-key"},
            timeout=10,
        )

    @patch("services.radarr_service.requests.get")
    def test_get_command_status_rejects_invalid_ids_before_get(self, get):
        for command_id in (None, "987", True, False, 0, -1, 1.5):
            with self.subTest(command_id=command_id):
                with self.assertRaisesRegex(
                    RadarrServiceError, "positive integer command ID"
                ):
                    self.service.get_command_status(command_id)
        get.assert_not_called()

    @patch("services.radarr_service.requests.get")
    def test_get_command_status_rejects_missing_or_wrong_response_id(self, get):
        for payload in ({"status": "completed"}, {"id": 986}, {"id": True}):
            with self.subTest(payload=payload):
                get.return_value.json.return_value = payload
                with self.assertRaisesRegex(
                    RadarrServiceError, "must match the requested command ID"
                ):
                    self.service.get_command_status(987)

    @patch("services.radarr_service.requests.get")
    def test_get_command_status_fails_safely(self, get):
        get.return_value.raise_for_status.side_effect = requests.HTTPError("bad")
        with self.assertRaises(requests.HTTPError):
            self.service.get_command_status(987)

        get.return_value.raise_for_status.side_effect = None
        get.return_value.json.return_value = []
        with self.assertRaisesRegex(RadarrServiceError, "JSON object"):
            self.service.get_command_status(987)


if __name__ == "__main__":
    unittest.main()
