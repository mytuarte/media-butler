import requests

from config import Config
from models.media_result import MediaResult
from services.search.search_service import SearchService


class RadarrSearchService(SearchService):
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

            release_date = (
                movie.get("digitalRelease")
                or movie.get("physicalRelease")
                or movie.get("inCinemas")
                or movie.get("minimumAvailability")
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
                    status=movie.get("status", "unknown"),
                    is_available=movie.get("isAvailable", False),
                    tmdb_id=movie.get("tmdbId"),
                    release_date=release_date,
                )
            )

        return results

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