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
            # Only process movie requests
            if request.get("type") != "movie":
                continue

            media = request.get(
                "media",
                {},
            )

            tmdb_id = media.get(
                "tmdbId",
            )

            if tmdb_id is None:
                continue

            requested_date = self._get_request_date(
                request,
            )

            if requested_date is None:
                continue

            waiting_time = now - requested_date

            if waiting_time < timedelta(hours=self.REQUEST_THRESHOLD_HOURS):
                continue

            title = self._get_request_title(
                request,
            )

            movie = movies_by_tmdb.get(
                tmdb_id,
            )

            if movie is None:
                if self._is_released_request(
                    request,
                ):
                    issues.append(
                        HealthIssue(
                            title=f"Pipeline Stalled: {title}",
                            issue_type="pipeline",
                            details=(
                                "Movie appears stuck before entering Radarr.\n\n"
                                f"Movie: {title}\n"
                                f"TMDb ID: {tmdb_id}\n\n"
                                f"Requested: {requested_date:%Y-%m-%d %H:%M}\n"
                                f"Waiting: {self._format_duration(waiting_time)}\n\n"
                                "Status:\n"
                                "- Overseerr Request: Yes\n"
                                "- Radarr Entry: Missing\n"
                                "- File Exists: No\n\n"
                                "Possible causes:\n"
                                "- Radarr sync failed\n"
                                "- Movie was removed from Radarr\n"
                                "- Request was never added"
                            ),
                            created_at=now,
                            severity="warning",
                        )
                    )

                continue

            if movie.get("hasFile"):
                continue

            if not movie.get("monitored"):
                continue

            if movie.get("status") != "released":
                continue

            if not movie.get("isAvailable"):
                continue

            if self._is_in_queue(
                title,
                queue_titles,
            ):
                continue

            history_details = self._build_history_details(
                movie.get("id"),
            )

            issues.append(
                HealthIssue(
                    title=f"Pipeline Stalled: {title}",
                    issue_type="pipeline",
                    details=(
                        "Movie appears stuck in acquisition pipeline.\n\n"
                        f"Movie: {title}\n"
                        f"TMDb ID: {tmdb_id}\n\n"
                        f"Requested: {requested_date:%Y-%m-%d %H:%M}\n"
                        f"Waiting: {self._format_duration(waiting_time)}\n\n"
                        "Status:\n"
                        "- Released: Yes\n"
                        "- Digital Available: Yes\n"
                        "- Radarr Monitored: Yes\n"
                        "- File Exists: No\n"
                        "- Download Queue: Not Found\n\n"
                        f"{history_details}\n\n"
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

    def _get_request_title(
        self,
        request: dict,
    ) -> str:
        media = request.get(
            "media",
            {},
        )

        return (
            media.get("title")
            or request.get("title")
            or request.get("name")
            or "Unknown Movie"
        )

    def _is_released_request(
        self,
        request: dict,
    ) -> bool:
        media = request.get(
            "media",
            {},
        )

        return (
            media.get(
                "status",
            )
            == 5
        )

    def _build_history_details(
        self,
        movie_id: int | None,
    ) -> str:
        if movie_id is None:
            return "Radarr History:\n" "Movie ID unavailable."

        history = self.radarr.get_recent_history(
            movie_id,
        )

        if not history:
            return "Radarr History:\n" "No recent activity found."

        latest = history[0]

        event = latest.get(
            "eventType",
            "Unknown",
        )

        date = latest.get(
            "date",
            "Unknown",
        )

        data = latest.get(
            "data",
            {},
        )

        return (
            "Radarr History:\n"
            f"Last Event: {event}\n"
            f"Date: {date}\n"
            f"Release Group: {data.get('releaseGroup', 'Unknown')}\n"
            f"Download Client: {data.get('downloadClientName', 'Unknown')}"
        )

    def _get_request_date(
        self,
        request: dict,
    ) -> datetime | None:
        requested_date = request.get(
            "createdAt",
        )

        if requested_date is None:
            return None

        return datetime.fromisoformat(
            requested_date.replace(
                "Z",
                "+00:00",
            )
        ).replace(
            tzinfo=None,
        )

    def _format_duration(
        self,
        duration: timedelta,
    ) -> str:
        hours = int(duration.total_seconds() // 3600)

        days = hours // 24
        hours %= 24

        if days:
            return f"{days} days, {hours} hours"

        return f"{hours} hours"

    def _is_in_queue(
        self,
        title: str,
        queue_titles: list[str],
    ) -> bool:
        title = title.lower()

        return any(title in queue_title for queue_title in queue_titles)
