from models.notification import MovieNotification
from services.overseerr_service import OverseerrService

import json
import requests

from config import Config


class SonarrService:
    def __init__(self):
        self.overseerr = OverseerrService()

    def parse_notification(self, payload: dict) -> MovieNotification:
        series = payload["series"]
        episode = payload["episodes"][0]
        episode_file = payload["episodeFiles"][0]

        tmdb_id = series.get("tmdbId")

        requester = self.overseerr.get_requester(tmdb_id)

        return MovieNotification(
            title=f"{series['title']} - "
                  f"S{episode['seasonNumber']:02d}"
                  f"E{episode['episodeNumber']:02d} - "
                  f"{episode['title']}",
            year=series["year"],
            requester=requester,
            quality=episode_file.get("quality", "Unknown"),
        )