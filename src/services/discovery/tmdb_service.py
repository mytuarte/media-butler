from datetime import date, timedelta

import requests

from config import Config
from models.discovery.discovery_item import DiscoveryItem


class TmdbService:
    BASE_URL = "https://api.themoviedb.org/3"
    WATCH_PROVIDER_REGION = "US"

    def get_trending_movies(self, pages: int = 1) -> list[DiscoveryItem]:
        """Return TMDB's popularity-ranked movies across the requested pages."""
        results = []

        for page in range(1, pages + 1):
            response = requests.get(
                f"{self.BASE_URL}/trending/movie/week",
                params={
                    "api_key": Config.TMDB_API_KEY,
                    "page": page,
                },
                timeout=30,
            )
            response.raise_for_status()

            for movie in response.json().get("results", []):
                results.append(self._movie_item(movie))

        return results

    def movie_has_digital_availability(
        self,
        tmdb_id: int,
        region: str = WATCH_PROVIDER_REGION,
    ) -> bool:
        """Whether TMDB lists subscription, rental, or purchase options.

        TMDB watch providers distinguish digital options from theatrical
        releases, so this must not be inferred from a movie's release date or
        any local Media Butler state.
        """
        response = requests.get(
            f"{self.BASE_URL}/movie/{tmdb_id}/watch/providers",
            params={"api_key": Config.TMDB_API_KEY},
            timeout=30,
        )
        response.raise_for_status()

        regional_providers = response.json().get("results", {}).get(region, {})
        return any(
            regional_providers.get(availability_type)
            for availability_type in ("flatrate", "rent", "buy")
        )

    @staticmethod
    def _movie_item(movie: dict) -> DiscoveryItem:
        return DiscoveryItem(
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

    def get_trending_tv(self, pages: int = 1) -> list[DiscoveryItem]:
        """Return TMDB's popularity-ranked TV shows across requested pages."""
        results = []

        for page in range(1, pages + 1):
            response = requests.get(
                f"{self.BASE_URL}/trending/tv/week",
                params={
                    "api_key": Config.TMDB_API_KEY,
                    "page": page,
                },
                timeout=30,
            )
            response.raise_for_status()

            for show in response.json().get("results", []):
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

    def tv_has_digital_availability(
        self,
        tmdb_id: int,
        region: str = WATCH_PROVIDER_REGION,
    ) -> bool:
        """Whether TMDB lists subscription, rental, or purchase TV options."""
        response = requests.get(
            f"{self.BASE_URL}/tv/{tmdb_id}/watch/providers",
            params={"api_key": Config.TMDB_API_KEY},
            timeout=30,
        )
        response.raise_for_status()

        regional_providers = response.json().get("results", {}).get(region, {})
        return any(
            regional_providers.get(availability_type)
            for availability_type in ("flatrate", "rent", "buy")
        )

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
