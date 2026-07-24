"""Normalized, read-only downgrade discovery data."""
from dataclasses import dataclass, field


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
