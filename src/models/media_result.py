from dataclasses import dataclass, field

from models.download_status import DownloadStatus
from models.overseerr_request import OverseerrRequest
from models.season_status import SeasonStatus


@dataclass
class MediaResult:
    id: int
    media_type: str
    title: str
    year: int

    has_file: bool
    monitored: bool

    quality: str
    status: str
    is_available: bool

    # External IDs
    tmdb_id: int | None = None

    # Release Information
    release_date: str | None = None

    # Overseerr
    overseerr: OverseerrRequest | None = None

    # Download Queue
    download: DownloadStatus | None = None

    # TV Progress
    downloaded_episodes: int = 0
    total_episodes: int = 0

    season_statuses: list[SeasonStatus] = field(default_factory=list)