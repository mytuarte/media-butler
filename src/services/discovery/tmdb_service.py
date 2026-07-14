import requests

from config import Config


class TmdbService:
    BASE_URL = "https://api.themoviedb.org/3"

    def get_trending_movies(self):
        response = requests.get(
            f"{self.BASE_URL}/trending/movie/week",
            headers={
                "Authorization": (
                    f"Bearer {Config.TMDB_API_KEY}"
                )
            },
            timeout=10,
        )

        response.raise_for_status()

        return response.json()