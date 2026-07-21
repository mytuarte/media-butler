from datetime import date, timedelta

import requests

from config import Config
from models.discovery.discovery_item import DiscoveryItem


class TmdbService:
    BASE_URL = "https://api.themoviedb.org/3"

    def get_trending_movies(self) -> list[DiscoveryItem]:
        response = requests.get(
            f"{self.BASE_URL}/trending/movie/week",
            params={
                "api_key": Config.TMDB_API_KEY,
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for movie in data["results"]:
            results.append(
                DiscoveryItem(
                    title=movie["title"],
                    media_type="movie",
                    tmdb_id=movie["id"],
                    release_date=movie.get("release_date"),
                    poster_url=(
                        f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
                        if movie.get("poster_path")
                        else None
                    ),
                    overview=movie.get("overview"),
                )
            )

        return results

    def get_trending_tv(self) -> list[DiscoveryItem]:
        response = requests.get(
            f"{self.BASE_URL}/trending/tv/week",
            params={
                "api_key": Config.TMDB_API_KEY,
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for show in data["results"]:
            results.append(
                DiscoveryItem(
                    title=show["name"],
                    media_type="tv",
                    tmdb_id=show["id"],
                    release_date=show.get("first_air_date"),
                    poster_url=(
                        f"https://image.tmdb.org/t/p/w500{show['poster_path']}"
                        if show.get("poster_path")
                        else None
                    ),
                    overview=show.get("overview"),
                )
            )

        return results

    def get_digital_movies(self) -> list[DiscoveryItem]:
        today = date.today()
        start_date = today - timedelta(days=30)

        response = requests.get(
            f"{self.BASE_URL}/discover/movie",
            params={
                "api_key": Config.TMDB_API_KEY,
                "region": "US",
                "sort_by": "popularity.desc",
                "with_release_type": 4,
                "vote_count.gte": 50,
                "release_date.gte": start_date.isoformat(),
                "release_date.lte": today.isoformat(),
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for movie in data["results"]:
            results.append(
                DiscoveryItem(
                    title=movie["title"],
                    media_type="movie",
                    tmdb_id=movie["id"],
                    release_date=movie.get("release_date"),
                    poster_url=(
                        f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
                        if movie.get("poster_path")
                        else None
                    ),
                    overview=movie.get("overview"),
                )
            )

        return results
