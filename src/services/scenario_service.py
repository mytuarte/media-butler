from datetime import date, datetime, timedelta, UTC

from models.media_result import MediaResult
from models.overseerr_request import OverseerrRequest


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