from config import Config

import requests

from models.notification import MovieNotification
from services.overseerr_service import OverseerrService


class SonarrService:
    def __init__(self):
        self.overseerr = OverseerrService()

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