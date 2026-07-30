"""Normalized downgrade candidate and suppression state."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class ReplacementCandidate:
    title: str
    size_bytes: int
    quality: str | None
    resolution: str | None
    video_codec: str | None
    languages: list[str] = field(default_factory=list)
    indexer: str | None = None
    protocol: str | None = None
    custom_format_score: int | None = None
    savings_bytes: int = 0
    savings_percent: int = 0
    release_name: str | None = None
    guid: str | None = None
    indexer_id: int | None = None


@dataclass
class DowngradeSuppression:
    movie_id: int
    guid: str
    release_name: str
    indexer_id: int | None = None
    download_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**value)
