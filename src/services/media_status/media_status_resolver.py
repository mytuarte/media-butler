from datetime import datetime

from models.monitoring_state import MonitoringState


class MediaStatusResolver:
    @staticmethod
    def resolve_movie(
        movie: dict,
    ) -> tuple[MonitoringState, str | None]:
        if movie.get("hasFile", False):
            return (
                MonitoringState.AVAILABLE,
                None,
            )

        if movie.get("monitored", False):
            status = movie.get("status", "")

            match status:
                case "announced":
                    detail = "Announced"

                case "inCinemas":
                    detail = "In Theaters"

                case _:
                    detail = (
                        status.replace("_", " ").replace("-", " ").title()
                        if status
                        else "Monitored"
                    )

            return (
                MonitoringState.COMING_SOON,
                detail,
            )

        return (
            MonitoringState.NOT_ADDED,
            None,
        )

    @staticmethod
    def resolve_series(
        series: dict,
    ) -> tuple[MonitoringState, str | None]:
        status = series.get("status", "")

        detail = None

        if status == "continuing":
            next_airing = series.get("nextAiring")

            if next_airing:
                detail = "Next: " + MediaStatusResolver._format_date(next_airing)
            else:
                detail = "Continuing"

        elif status == "ended":
            detail = "Ended"

        elif status == "upcoming":
            detail = "Awaiting Premiere"

        elif status:
            detail = status.replace("_", " ").replace("-", " ").title()

        if (
            series.get("statistics", {}).get(
                "sizeOnDisk",
                0,
            )
            > 0
        ):
            return (
                MonitoringState.AVAILABLE,
                detail,
            )

        if series.get("monitored", False):
            return (
                MonitoringState.COMING_SOON,
                detail or "Monitored",
            )

        return (
            MonitoringState.NOT_ADDED,
            None,
        )

    @staticmethod
    def _format_date(
        date_string: str,
    ) -> str:
        date = datetime.fromisoformat(date_string.replace("Z", "+00:00"))

        return date.strftime("%b %d")
