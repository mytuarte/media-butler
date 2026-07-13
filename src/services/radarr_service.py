from models.notification import MovieNotification
from services.overseerr_service import OverseerrService

from config import Config

import requests


class RadarrService:
    def __init__(self):
        self.overseerr = OverseerrService()

    def parse_notification(self, payload: dict) -> MovieNotification:
        movie = payload["movie"]

        tmdb_id = movie.get("tmdbId")

        requester = self.overseerr.get_requester(tmdb_id)

        quality = "Unknown"

        movie_file = payload.get("movieFile")
        if movie_file:
            quality = (
                movie_file.get("quality", {})
                .get("quality", {})
                .get("name", "Unknown")
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