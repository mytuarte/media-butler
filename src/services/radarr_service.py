import requests

from config import Config
from models.media_result import MediaResult
from models.notification import MovieNotification
from services.overseerr_service import OverseerrService


class RadarrService:
    def __init__(self):
        self.overseerr = OverseerrService()

    def parse_notification(self, payload: dict) -> MovieNotification:
        movie = payload["movie"]
        release = payload.get("release", {})

        tmdb_id = movie.get("tmdbId")

        requester = self.overseerr.get_requester(tmdb_id)

        return MovieNotification(
            title=movie["title"],
            year=movie["year"],
            requester=requester,
            quality=release.get("quality", "Unknown"),
        )

    def search(self, query: str) -> list[MediaResult]:
        headers = {
            "X-Api-Key": Config.RADARR_API_KEY,
        }

        response = requests.get(
            f"{Config.RADARR_URL}/api/v3/movie",
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        movies = response.json()

        query = query.lower()

        results = []

        for movie in movies:
            if query not in movie["title"].lower():
                continue

            quality = "Unknown"

            if movie.get("hasFile") and movie.get("movieFile"):
                quality = (
                    movie["movieFile"]
                    .get("quality", {})
                    .get("quality", {})
                    .get("name", "Unknown")
                )

            results.append(
                MediaResult(
                    id=movie["id"],
                    media_type="movie",
                    title=movie["title"],
                    year=movie["year"],
                    has_file=movie.get("hasFile", False),
                    monitored=movie.get("monitored", False),
                    quality=quality,
                )
            )

        return results