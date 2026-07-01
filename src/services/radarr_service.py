from models.notification import MovieNotification


class RadarrService:
    def parse_notification(self, payload: dict) -> MovieNotification:
        movie = payload["movie"]
        release = payload.get("release", {})

        return MovieNotification(
            title=movie["title"],
            year=movie["year"],
            requester="Unknown",
            quality=release.get("quality", "Unknown"),
        )