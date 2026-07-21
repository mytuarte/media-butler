import json

import requests

from config import Config
from models.monitoring_state import MonitoringState
from models.notification import MovieNotification
from services.media_status.media_status_resolver import (
    MediaStatusResolver,
)
from services.overseerr_service import OverseerrService


class SonarrService:
    def __init__(self):
        self.overseerr = OverseerrService()
        self._episode_cache: dict[int, list[dict]] = {}

    def parse_notification(self, payload: dict) -> MovieNotification:
        series = payload["series"]
        episode = payload["episodes"][0]
        episode_file = payload["episodeFiles"][0]

        tmdb_id = series.get("tmdbId")

        request = self.overseerr.get_request(tmdb_id)

        requester = None
        if request is not None:
            requester = request.requester

        return MovieNotification(
            title=(
                f"{series['title']} - "
                f"S{episode['seasonNumber']:02d}"
                f"E{episode['episodeNumber']:02d} - "
                f"{episode['title']}"
            ),
            year=series["year"],
            requester=requester,
            quality=episode_file.get("quality", "Unknown"),
        )

    def get_series(self):
        headers = {
            "X-Api-Key": Config.SONARR_API_KEY,
        }

        response = requests.get(
            f"{Config.SONARR_URL}/api/v3/series",
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def test_connection(self):
        headers = {
            "X-Api-Key": Config.SONARR_API_KEY,
        }

        response = requests.get(
            f"{Config.SONARR_URL}/api/v3/system/status",
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

    def get_episodes(
        self,
        series_id: int,
    ):
        if series_id in self._episode_cache:
            return self._episode_cache[series_id]

        headers = {
            "X-Api-Key": Config.SONARR_API_KEY,
        }

        response = requests.get(
            f"{Config.SONARR_URL}/api/v3/episode",
            headers=headers,
            params={
                "seriesId": series_id,
            },
            timeout=10,
        )

        response.raise_for_status()

        episodes = response.json()

        self._episode_cache[series_id] = episodes

        return episodes

    def get_episode_files(
        self,
        series_id: int,
    ):
        headers = {
            "X-Api-Key": Config.SONARR_API_KEY,
        }

        response = requests.get(
            f"{Config.SONARR_URL}/api/v3/episodefile",
            headers=headers,
            params={
                "seriesId": series_id,
            },
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def get_all_episode_files(self):
        files = []

        for series in self.get_series():
            try:
                series_files = self.get_episode_files(
                    series["id"],
                )

                for file in series_files:
                    file["series"] = series

                files.extend(series_files)

            except Exception:
                continue

        return files

    def get_history(self):
        headers = {
            "X-Api-Key": Config.SONARR_API_KEY,
        }

        response = requests.get(
            f"{Config.SONARR_URL}/api/v3/history",
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def get_monitoring_states(
        self,
    ) -> dict[int, tuple[MonitoringState, str | None]]:
        series = self.get_series()

        return {
            show["tmdbId"]: (MediaStatusResolver.resolve_series(show))
            for show in series
            if show.get("tmdbId") is not None
        }

    def debug_series(
        self,
        title: str,
    ):
        title = title.lower()

        for series in self.get_series():
            if title in series.get("title", "").lower():
                print("\n" + "=" * 80)
                print(f"{series.get('title')} ({series.get('year')})")
                print("=" * 80)
                print(json.dumps(series, indent=4))
                print("=" * 80 + "\n")
                return

        print(f'No series found matching "{title}"')
