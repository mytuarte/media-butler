import requests

from config import Config
from models.media_result import MediaResult
from models.season_status import SeasonStatus
from services.search.search_service import SearchService


class SonarrSearchService(SearchService):
    def search(self, query: str) -> list[MediaResult]:
        headers = {
            "X-Api-Key": Config.SONARR_API_KEY,
        }

        response = requests.get(
            f"{Config.SONARR_URL}/api/v3/series",
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        series_list = response.json()

        query = query.lower()

        results = []

        for series in series_list:
            if query not in series["title"].lower():
                continue

            statistics = series.get("statistics", {})

            downloaded_episodes = statistics.get(
                "episodeFileCount",
                0,
            )

            # Use released episodes instead of total known episodes.
            total_episodes = statistics.get(
                "episodeCount",
                0,
            )

            has_file = (
                total_episodes > 0
                and downloaded_episodes == total_episodes
            )

            season_statuses = []

            for season in series.get("seasons", []):
                season_number = season.get("seasonNumber", 0)

                # Ignore specials (Season 0)
                if season_number == 0:
                    continue

                season_stats = season.get("statistics", {})

                season_statuses.append(
                    SeasonStatus(
                        season_number=season_number,
                        downloaded_episodes=season_stats.get(
                            "episodeFileCount",
                            0,
                        ),
                        total_episodes=season_stats.get(
                            "episodeCount",
                            0,
                        ),
                    )
                )

            results.append(
                MediaResult(
                    id=series["id"],
                    media_type="series",
                    title=series["title"],
                    year=series["year"],
                    has_file=has_file,
                    monitored=series.get("monitored", False),
                    quality="Series",
                    status=series.get("status", "unknown"),
                    is_available=series.get("status") != "upcoming",
                    tmdb_id=series.get("tmdbId"),
                    overseerr=None,
                    downloaded_episodes=downloaded_episodes,
                    total_episodes=total_episodes,
                    season_statuses=season_statuses,
                )
            )

        return results