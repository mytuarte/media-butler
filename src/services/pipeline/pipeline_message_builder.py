from datetime import date, datetime, timezone

from models.media_result import MediaResult


class PipelineMessageBuilder:
    @staticmethod
    def build_ready_message(result: MediaResult) -> str:
        return "Available in Plex."

    @staticmethod
    def build_downloading_message(result: MediaResult) -> str:
        active_season = next(
            (
                season
                for season in result.season_statuses
                if season.is_partial
            ),
            None,
        )

        if active_season:
            return (
                f"Downloading Season "
                f"{active_season.season_number}."
            )

        return (
            f"{result.downloaded_episodes} of "
            f"{result.total_episodes} episodes downloaded."
        )

    @staticmethod
    def build_requested_message(result: MediaResult) -> str:
        if result.media_type == "movie":
            return "Request received."

        return "Waiting for Sonarr."

    @staticmethod
    def build_awaiting_release_message(
        result: MediaResult,
    ) -> str:
        return PipelineMessageBuilder._build_movie_release_message(
            result
        )

    @staticmethod
    def build_wanted_message(result: MediaResult) -> str:
        return "Monitored but no request exists."

    @staticmethod
    def build_not_monitored_message(
        result: MediaResult,
    ) -> str:
        return "Media is not monitored."

    @staticmethod
    def _build_movie_release_message(
        result: MediaResult,
    ) -> str:
        if not result.release_date:
            return "Waiting for the official release."

        release = result.release_date

        if isinstance(release, str):
            try:
                release = datetime.fromisoformat(
                    release.replace("Z", "+00:00")
                ).date()
            except ValueError:
                return "Waiting for the official release."

        if not isinstance(release, date):
            return "Waiting for the official release."

        today = datetime.now(timezone.utc).date()
        delta = (release - today).days

        if delta > 1:
            return (
                f"Releases in {delta} days "
                f"({release:%b %d, %Y})."
            )

        if delta == 1:
            return "Releases tomorrow."

        if delta == 0:
            return "Releases today."

        days = abs(delta)

        if days == 1:
            return "Released yesterday."

        return f"Released {days} days ago."