import requests

from config import Config
from models.discovery.discovery_item import DiscoveryItem


class TmdbService:
    BASE_URL = "https://api.themoviedb.org/3"

    def get_trending_movies(self):
        response = requests.get(
            f"{self.BASE_URL}/trending/movie/week",
            params={
                "api_key": Config.TMDB_API_KEY,
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        movies = []

        for movie in data["results"]:
            movies.append(
                DiscoveryItem(
                    title=movie["title"],
                    media_type="movie",
                    release_date=movie.get("release_date"),
                )
            )

        return movies
