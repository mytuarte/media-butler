"""Normalized downgrade candidate and persistent downgrade state."""
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


DOWNGRADE_OPERATION_STATES = frozenset({
    "submitting", "waiting_for_download", "inspecting_import",
    "manual_import_ready", "automatic_import_detected", "blocked", "ambiguous",
})


@dataclass
class DowngradeOperation:
    movie_id: int
    selected_release_name: str
    selected_release_guid: str
    selected_indexer_id: int
    selected_release_size: int
    selected_protocol: str
    original_movie_file_id: int
    original_file_path: str
    original_file_size: int
    original_quality: dict | str | None
    state: str = "submitting"
    download_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_safe_diagnostic_reason: str = "Original movie file snapshot captured"

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, value: dict):
        if not isinstance(value, dict):
            raise ValueError("operation must be an object")
        record = cls(**value)
        positive = (
            record.movie_id, record.selected_indexer_id, record.selected_release_size,
            record.original_movie_file_id, record.original_file_size,
        )
        if any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in positive):
            raise ValueError("operation IDs and sizes must be positive integers")
        required_text = (
            record.selected_release_name, record.selected_release_guid,
            record.selected_protocol, record.original_file_path,
            record.created_at, record.updated_at, record.last_safe_diagnostic_reason,
        )
        if any(not isinstance(item, str) or not item.strip() for item in required_text):
            raise ValueError("operation text fields must be non-empty")
        if record.download_id is not None and (
            not isinstance(record.download_id, str) or not record.download_id.strip()
        ):
            raise ValueError("download ID must be non-empty when present")
        if record.state not in DOWNGRADE_OPERATION_STATES:
            raise ValueError("unsupported operation state")
        for timestamp in (record.created_at, record.updated_at):
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None:
                raise ValueError("operation timestamps must include a timezone")
        if record.original_quality is not None and not isinstance(record.original_quality, (dict, str)):
            raise ValueError("original quality must be an object, string, or null")
        return record
