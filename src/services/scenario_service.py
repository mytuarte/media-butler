from datetime import UTC, date, datetime, timedelta

from models.media_result import MediaResult
from models.overseerr_request import OverseerrRequest
from models.season_status import SeasonStatus


class ScenarioService:
    @staticmethod
    def released_not_downloaded() -> MediaResult:
        return MediaResult(
            id=1,
            media_type="movie",
            title="Scenario Movie",
            year=2026,
            has_file=False,
            monitored=True,
            quality="Unknown",
            status="released",
            is_available=False,
            tmdb_id=0,
            release_date=date.today() - timedelta(days=12),
            overseerr=OverseerrRequest(
                id=1,
                status=2,
                media_status=3,
                requester="Michael",
                requester_discord_id=None,
                requested_date=(
                    datetime.now(UTC) - timedelta(days=12)
                ).isoformat(),
                raw={},
            ),
        )

    @staticmethod
    def awaiting_release() -> MediaResult:
        return MediaResult(
            id=2,
            media_type="movie",
            title="Future Movie",
            year=date.today().year,
            has_file=False,
            monitored=True,
            quality="Unknown",
            status="announced",
            is_available=False,
            tmdb_id=0,
            release_date=date.today() + timedelta(days=18),
            overseerr=OverseerrRequest(
                id=2,
                status=2,
                media_status=1,
                requester="Michael",
                requester_discord_id=None,
                requested_date=datetime.now(UTC).isoformat(),
                raw={},
            ),
        )

    @staticmethod
    def downloading_series() -> MediaResult:
        return MediaResult(
            id=3,
            media_type="series",
            title="Scenario Series",
            year=2026,
            has_file=False,
            monitored=True,
            quality="Unknown",
            status="continuing",
            is_available=False,
            tmdb_id=0,
            downloaded_episodes=6,
            total_episodes=10,
            season_statuses=[
                SeasonStatus(
                    season_number=1,
                    downloaded_episodes=6,
                    total_episodes=10,
                ),
            ],
            overseerr=OverseerrRequest(
                id=3,
                status=2,
                media_status=3,
                requester="Michael",
                requester_discord_id=None,
                requested_date=(
                    datetime.now(UTC) - timedelta(days=5)
                ).isoformat(),
                raw={},
            ),
        )
