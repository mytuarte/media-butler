import json

import requests

from config import Config
from models.monitoring_state import MonitoringState
from models.notification import MovieNotification
from services.media_status.media_status_resolver import (
    MediaStatusResolver,
)
from services.overseerr_service import OverseerrService


class RadarrService:
    def __init__(self):
        self.overseerr = OverseerrService()

    def parse_notification(self, payload: dict) -> MovieNotification:
        movie = payload["movie"]

        tmdb_id = movie.get("tmdbId")

        request = self.overseerr.get_request(tmdb_id)

        requester = None
        if request is not None:
            requester = request.requester

        quality = "Unknown"

        movie_file = payload.get("movieFile")
        if movie_file:
            quality = (
                movie_file.get("quality", {}).get("quality", {}).get("name", "Unknown")
            )

        return MovieNotification(
            title=movie["title"],
            year=movie["year"],
            requester=requester,
            quality=quality,
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

    def get_monitoring_states(
        self,
    ) -> dict[int, tuple[MonitoringState, str | None]]:
        movies = self.get_movies()

        return {
            movie["tmdbId"]: (MediaStatusResolver.resolve_movie(movie))
            for movie in movies
            if movie.get("tmdbId") is not None
        }

    def delete_movie(self, movie_id: int):
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

    def debug_movie(self, title: str):
        title = title.lower()

        for movie in self.get_movies():
            if title in movie.get("title", "").lower():
                print("\n" + "=" * 80)
                print(f"{movie.get('title')} ({movie.get('year')})")
                print("=" * 80)
                print(json.dumps(movie, indent=4))
                print("=" * 80 + "\n")
                return

        print(f'No movie found matching "{title}"')
