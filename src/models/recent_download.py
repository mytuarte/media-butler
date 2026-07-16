from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RecentDownload:
    title: str
    media_type: str

    downloaded_date: datetime

    size_bytes: int

    quality: str

    requester: str | None = None

    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None

    episodes: list[tuple[int, int, str | None]] = field(default_factory=list)
