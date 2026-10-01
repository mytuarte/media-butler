from datetime import date, timedelta

import requests

from config import Config
from models.discovery.discovery_details import DiscoveryDetails
from models.discovery.discovery_item import DiscoveryItem


class TmdbService:
    BASE_URL = "https://api.themoviedb.org/3"
    WATCH_PROVIDER_REGION = "US"
    STREAMING_PROVIDER_TYPES = ("flatrate", "free", "ads")

    def get_details(
        self,
        media_type: str,
        tmdb_id: int,
        region: str = WATCH_PROVIDER_REGION,
    ) -> DiscoveryDetails:
        """Return the current TMDB summary, rating, and streaming providers."""
        if media_type not in {"movie", "tv"}:
            raise ValueError("TMDB details media type must be movie or tv.")

        if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool) or tmdb_id <= 0:
            raise ValueError("TMDB details ID must be positive.")

        response = requests.get(
            f"{self.BASE_URL}/{media_type}/{tmdb_id}",
            params={
                "api_key": Config.TMDB_API_KEY,
                "append_to_response": "watch/providers",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        regional_providers = (
            payload.get("watch/providers", {})
            .get("results", {})
            .get(region, {})
        )
        title = payload.get("title") or payload.get("name") or "Untitled"
        release_date = payload.get("release_date") or payload.get("first_air_date")
        vote_average = payload.get("vote_average")
        vote_count = payload.get("vote_count")

        return DiscoveryDetails(
            title=title,
            media_type=media_type,
            tmdb_id=tmdb_id,
            overview=payload.get("overview"),
            vote_average=(
                float(vote_average)
                if isinstance(vote_average, (int, float))
                and not isinstance(vote_average, bool)
                else None
            ),
            vote_count=(
                int(vote_count)
                if isinstance(vote_count, int) and not isinstance(vote_count, bool)
                else None
            ),
            poster_url=(
                f"https://image.tmdb.org/t/p/w500{payload['poster_path']}"
                if payload.get("poster_path")
                else None
            ),
            release_date=release_date,
            streaming_providers=self._streaming_provider_names(regional_providers),
        )

    @classmethod
    def _streaming_provider_names(cls, regional_providers: dict) -> tuple[str, ...]:
        names = []
        seen = set()

        for provider_type in cls.STREAMING_PROVIDER_TYPES:
            for provider in regional_providers.get(provider_type, []) or []:
                name = (
                    provider.get("provider_name")
                    if isinstance(provider, dict)
                    else None
                )
                if isinstance(name, str) and name and name not in seen:
                    names.append(name)
                    seen.add(name)

        return tuple(names)

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
