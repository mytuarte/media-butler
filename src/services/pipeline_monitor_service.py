from datetime import datetime, timedelta

from models.health_issue import HealthIssue
from services.overseerr_service import OverseerrService
from services.radarr_service import RadarrService
from services.sabnzbd_client import SabnzbdClient


class PipelineMonitorService:
    REQUEST_THRESHOLD_HOURS = 24

    def __init__(self):
        self.overseerr = OverseerrService()
        self.radarr = RadarrService()
        self.sabnzbd = SabnzbdClient()

    def check_movies(self) -> list[HealthIssue]:
        issues: list[HealthIssue] = []

        requests = self.overseerr.get_requests()["results"]

        movies = self.radarr.get_movies()

        movies_by_tmdb = {
            movie.get("tmdbId"): movie
            for movie in movies
            if movie.get("tmdbId") is not None
        }

        queue = self.sabnzbd.get_queue()

        queue_titles = [
            slot.get(
                "filename",
                "",
            ).lower()
            for slot in queue.get(
                "queue",
                {},
            ).get(
                "slots",
                [],
            )
        ]

        now = datetime.now()

        for request in requests:
            media = request.get(
                "media",
                {},
            )

            tmdb_id = media.get("tmdbId")

            if tmdb_id is None:
                continue

            movie = movies_by_tmdb.get(tmdb_id)

            if movie is None:
                continue

            if movie.get("hasFile"):
                continue

            if not movie.get("monitored"):
                continue

            if movie.get("status") != "released":
                continue

            if not movie.get("isAvailable"):
                continue

            if not self._is_old_request(
                request,
                now,
            ):
                continue

            title = movie.get(
                "title",
                "Unknown Movie",
            )

            if self._is_in_queue(
                title,
                queue_titles,
            ):
                continue

            issues.append(
                HealthIssue(
                    title=f"Pipeline: {title}",
                    issue_type="pipeline",
                    details=(
                        "Movie appears stuck in acquisition pipeline.\n\n"
                        f"Movie: {title}\n"
                        "Requested: Yes\n"
                        "Released: Yes\n"
                        "Digital Available: Yes\n"
                        "Radarr Monitored: Yes\n"
                        "File Exists: No\n"
                        "Download Queue: Not Found\n\n"
                        "Possible causes:\n"
                        "- Radarr has not found a release\n"
                        "- Indexers returned no results\n"
                        "- Download failed before entering queue"
                    ),
                    created_at=now,
                    severity="warning",
                )
            )

        return issues

    def _is_old_request(
        self,
        request: dict,
        now: datetime,
    ) -> bool:
        requested_date = request.get("createdAt")

        if requested_date is None:
            return False

        created = datetime.fromisoformat(
            requested_date.replace(
                "Z",
                "+00:00",
            )
        ).replace(
            tzinfo=None,
        )

        return now - created >= timedelta(hours=self.REQUEST_THRESHOLD_HOURS)

    def _is_in_queue(
        self,
        title: str,
        queue_titles: list[str],
    ) -> bool:
        title = title.lower()

        return any(title in queue_title for queue_title in queue_titles)
