from config import Config
from models.notification import MovieNotification
from services.overseerr_service import OverseerrService


class RadarrService:
    def __init__(self):
        self.overseerr = OverseerrService()

    def parse_notification(self, payload: dict) -> MovieNotification:
        movie = payload["movie"]
        release = payload.get("release", {})

        tmdb_id = movie.get("tmdbId")

        requester = self.overseerr.get_requester(tmdb_id)

        return MovieNotification(
            title=movie["title"],
            year=movie["year"],
            requester=requester,
            quality=release.get("quality", "Unknown"),
        )