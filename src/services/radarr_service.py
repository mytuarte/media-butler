import json
from pathlib import PurePosixPath

import requests

from config import Config
from models.monitoring_state import MonitoringState
from models.notification import MovieNotification
from services.media_status.media_status_resolver import (
    MediaStatusResolver,
)
from services.overseerr_service import OverseerrService


class RadarrServiceError(ValueError):
    """Raised when Radarr returns invalid data or an import request is unsafe."""


class RadarrService:
    def __init__(self):
        self.overseerr = OverseerrService()

    def parse_notification(self, payload: dict) -> MovieNotification:
        movie = payload["movie"]

        tmdb_id = movie.get("tmdbId")

        request = self.overseerr.get_request(tmdb_id)

        requester = (
            request.requester_discord_id
            if request is not None and isinstance(request.requester_discord_id, int)
            else request.requester if request is not None else None
        )

        movie_file = payload.get("movieFile", {})
        quality = self._parse_quality(movie_file)

        return MovieNotification(
            title=movie["title"],
            year=movie["year"],
            requester=requester,
            quality=quality,
        )

    @staticmethod
    def _parse_quality(movie_file: object) -> str:
        if not isinstance(movie_file, dict):
            return "Unknown"

        quality = movie_file.get("quality")

        if isinstance(quality, str):
            return quality or "Unknown"

        if not isinstance(quality, dict):
            return "Unknown"

        direct_name = quality.get("name")
        if isinstance(direct_name, str) and direct_name:
            return direct_name

        nested_quality = quality.get("quality")
        if not isinstance(nested_quality, dict):
            return "Unknown"

        nested_name = nested_quality.get("name")
        return (
            nested_name if isinstance(nested_name, str) and nested_name else "Unknown"
        )

    def get_movies(self):
        headers = {
            "X-Api-Key": Config.RADARR_API_KEY,
        }

        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/movie",
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def test_connection(self):
        headers = {
            "X-Api-Key": Config.RADARR_API_KEY,
        }

        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/system/status",
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

    def get_history(self):
        headers = {
            "X-Api-Key": Config.RADARR_API_KEY,
        }

        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/history",
            headers=headers,
            params={
                "pageSize": 100,
                "sortKey": "date",
                "sortDirection": "descending",
            },
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def get_recent_history(
        self,
        movie_id: int,
        limit: int = 10,
    ):
        history = self.get_history()

        records = [
            item
            for item in history.get(
                "records",
                [],
            )
            if item.get("movieId") == movie_id
        ]

        return records[:limit]

    def get_monitoring_states(
        self,
    ) -> dict[int, tuple[MonitoringState, str | None]]:
        movies = self.get_movies()

        return {
            movie["tmdbId"]: (MediaStatusResolver.resolve_movie(movie))
            for movie in movies
            if movie.get("tmdbId") is not None
        }

    def delete_movie(
        self,
        movie_id: int,
    ):
        headers = {
            "X-Api-Key": Config.RADARR_API_KEY,
        }

        response = requests.delete(
            f"{Config.RADARR_URL}/api/v3/movie/{movie_id}",
            headers=headers,
            params={
                "deleteFiles": True,
                "addImportExclusion": False,
            },
            timeout=10,
        )

        response.raise_for_status()

    def debug_movie(
        self,
        title: str,
    ):
        title = title.lower()

        for movie in self.get_movies():
            if (
                title
                in movie.get(
                    "title",
                    "",
                ).lower()
            ):
                print("\n" + "=" * 80)
                print(f"{movie.get('title')} ({movie.get('year')})")
                print("=" * 80)
                print(
                    json.dumps(
                        movie,
                        indent=4,
                    )
                )
                print("=" * 80 + "\n")

                return

        print(f'No movie found matching "{title}"')

    def get_movie_by_id(self, movie_id: int) -> dict | None:
        """Read one Radarr movie record; analysis must not scan the library."""
        if not isinstance(movie_id, int) or isinstance(movie_id, bool) or movie_id <= 0:
            raise RadarrServiceError("Radarr movie lookup requires a positive movie ID")
        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/movie/{movie_id}",
            headers={"X-Api-Key": Config.RADARR_API_KEY},
            timeout=10,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RadarrServiceError("Radarr movie response must be an object")
        response_id = payload.get("id")
        if (
            not isinstance(response_id, int)
            or isinstance(response_id, bool)
            or response_id <= 0
            or response_id != movie_id
        ):
            raise RadarrServiceError("Radarr movie response ID must match the requested movie ID")
        return payload

    def get_movie_file_snapshot(self, movie_id: int) -> dict:
        """Return the authoritative current movie/file data used by a downgrade."""
        movie = self.get_movie_by_id(movie_id)
        if movie is None:
            raise RadarrServiceError("Radarr movie does not exist")
        file_id = movie.get("movieFileId")
        movie_file = movie.get("movieFile")
        nested_file_id = movie_file.get("id") if isinstance(movie_file, dict) else None
        nested_movie_id = movie_file.get("movieId") if isinstance(movie_file, dict) else None
        if (
            not isinstance(file_id, int) or isinstance(file_id, bool) or file_id <= 0
            or not isinstance(nested_file_id, int) or isinstance(nested_file_id, bool)
            or nested_file_id <= 0 or nested_file_id != file_id
            or not isinstance(nested_movie_id, int) or isinstance(nested_movie_id, bool)
            or nested_movie_id <= 0 or nested_movie_id != movie_id
        ):
            raise RadarrServiceError("Radarr current movie file could not be identified")
        path = movie_file.get("path") or movie_file.get("relativePath")
        file_size = movie_file.get("size")
        if (
            not isinstance(path, str) or not path.strip()
            or not isinstance(file_size, int) or isinstance(file_size, bool) or file_size <= 0
        ):
            raise RadarrServiceError("Radarr current movie file snapshot is incomplete")
        return {
            "movie_id": movie_id,
            "movie_file_id": file_id,
            "path": path,
            "size": file_size,
            "quality": movie_file.get("quality"),
        }

    def manual_search(self, movie_id: int) -> list[dict]:
        """Return Radarr's read-only manual-search releases for a movie."""
        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/release",
            headers={"X-Api-Key": Config.RADARR_API_KEY},
            params={"movieId": movie_id}, timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def grab_release(self, release: dict) -> dict:
        """Submit exactly one object returned by the manual-search endpoint."""
        response = requests.post(
            f"{Config.RADARR_URL}/api/v3/release",
            headers={"X-Api-Key": Config.RADARR_API_KEY},
            json=release,
            timeout=15,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def get_queue(self) -> list[dict]:
        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/queue",
            headers={"X-Api-Key": Config.RADARR_API_KEY},
            params={"pageSize": 100, "includeUnknownMovieItems": "true"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("records", []) if isinstance(payload, dict) else []

    def get_manual_import_candidates(
        self,
        download_id: str,
        movie_id: int,
    ) -> list[dict]:
        """Retrieve Radarr's import candidates for one tracked download."""
        if not isinstance(download_id, str) or not download_id.strip():
            raise RadarrServiceError(
                "Radarr manual-import candidate lookup requires a download ID"
            )
        if (
            not isinstance(movie_id, int)
            or isinstance(movie_id, bool)
            or movie_id <= 0
        ):
            raise RadarrServiceError(
                "Radarr manual-import candidate lookup requires a positive movie ID"
            )

        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/manualimport",
            headers={"X-Api-Key": Config.RADARR_API_KEY},
            params={
                "downloadId": download_id,
                "movieId": movie_id,
                "filterExistingFiles": True,
            },
            timeout=10,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except (requests.exceptions.JSONDecodeError, ValueError) as error:
            raise RadarrServiceError(
                "Radarr manual-import response must be a JSON list of objects"
            ) from error

        if not isinstance(payload, list) or any(
            not isinstance(candidate, dict) for candidate in payload
        ):
            raise RadarrServiceError(
                "Radarr manual-import response must be a JSON list of objects"
            )

        return payload

    def submit_manual_import_candidate(
        self,
        candidate: dict,
        download_id: str,
        movie_id: int,
    ) -> dict:
        """Submit exactly one previously returned candidate to Radarr."""
        if not isinstance(download_id, str) or not download_id.strip():
            raise RadarrServiceError("Radarr manual import requires a download ID")
        if (
            not isinstance(movie_id, int)
            or isinstance(movie_id, bool)
            or movie_id <= 0
        ):
            raise RadarrServiceError("Radarr manual import requires a positive movie ID")
        if not isinstance(candidate, dict):
            raise RadarrServiceError("Radarr manual-import candidate must be an object")

        path = candidate.get("path")
        if (
            not isinstance(path, str)
            or not path.strip()
            or not PurePosixPath(path).is_absolute()
        ):
            raise RadarrServiceError(
                "Radarr manual-import candidate requires an absolute path"
            )

        movie = candidate.get("movie")
        if not isinstance(movie, dict) or movie.get("id") != movie_id:
            raise RadarrServiceError(
                "Radarr manual-import candidate movie ID does not match"
            )

        candidate_download_id = candidate.get("downloadId")
        if candidate_download_id is not None and candidate_download_id != download_id:
            raise RadarrServiceError(
                "Radarr manual-import candidate download ID does not match"
            )

        file_payload = {
            "path": path,
            "folderName": candidate.get("folderName"),
            "movieId": movie_id,
            "releaseGroup": candidate.get("releaseGroup"),
            "quality": candidate.get("quality"),
            "languages": candidate.get("languages"),
            "indexerFlags": candidate.get("indexerFlags"),
            "downloadId": download_id,
        }
        response = requests.post(
            f"{Config.RADARR_URL}/api/v3/command",
            headers={"X-Api-Key": Config.RADARR_API_KEY},
            json={
                "name": "ManualImport",
                "files": [file_payload],
                "importMode": "auto",
            },
            timeout=15,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except (requests.exceptions.JSONDecodeError, ValueError) as error:
            raise RadarrServiceError(
                "Radarr manual-import command response must be an object with an ID"
            ) from error
        if not isinstance(payload, dict):
            raise RadarrServiceError(
                "Radarr manual-import command response must be a JSON object"
            )

        command_id = payload.get("id")
        if (
            not isinstance(command_id, int)
            or isinstance(command_id, bool)
            or command_id <= 0
        ):
            raise RadarrServiceError(
                "Radarr manual-import command response must contain a positive integer ID"
            )
        return payload

    def get_command_status(self, command_id: int) -> dict:
        """Retrieve one Radarr command using its exact command ID."""
        if (
            not isinstance(command_id, int)
            or isinstance(command_id, bool)
            or command_id <= 0
        ):
            raise RadarrServiceError(
                "Radarr command status requires a positive integer command ID"
            )

        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/command/{command_id}",
            headers={"X-Api-Key": Config.RADARR_API_KEY},
            timeout=10,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except (requests.exceptions.JSONDecodeError, ValueError) as error:
            raise RadarrServiceError(
                "Radarr command-status response must be a JSON object"
            ) from error
        if not isinstance(payload, dict):
            raise RadarrServiceError(
                "Radarr command-status response must be a JSON object"
            )

        response_id = payload.get("id")
        if (
            not isinstance(response_id, int)
            or isinstance(response_id, bool)
            or response_id <= 0
            or response_id != command_id
        ):
            raise RadarrServiceError(
                "Radarr command-status response ID must match the requested command ID"
            )
        return payload
