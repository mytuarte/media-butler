from dataclasses import dataclass, field

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

    downloaded_episodes: int = 0
    total_episodes: int = 0

    season_statuses: list[SeasonStatus] = field(default_factory=list)