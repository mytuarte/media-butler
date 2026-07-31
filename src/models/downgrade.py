"""Normalized downgrade candidate and persistent downgrade state."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath


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
    "submitting_manual_import", "manual_import_submitted",
    "verifying_replacement", "replacement_verified", "manual_import_failed",
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
    replacement_candidate_path: str | None = None
    replacement_candidate_size: int | None = None
    replacement_candidate_quality: dict | None = None
    manual_import_command_id: int | None = None
    manual_import_submitted_at: str | None = None
    replacement_verified_at: str | None = None
    final_replacement_movie_file_id: int | None = None
    final_replacement_path: str | None = None
    final_replacement_size: int | None = None
    final_replacement_quality: dict | None = None

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
        candidate_values = (
            record.replacement_candidate_path,
            record.replacement_candidate_size,
            record.replacement_candidate_quality,
        )
        if any(value is not None for value in candidate_values):
            if not all(value is not None for value in candidate_values):
                raise ValueError("replacement candidate identity must be persisted together")
            if not isinstance(record.replacement_candidate_path, str) or not record.replacement_candidate_path.strip() or not PurePosixPath(record.replacement_candidate_path).is_absolute():
                raise ValueError("replacement candidate path must be an absolute POSIX path")
            if not isinstance(record.replacement_candidate_size, int) or isinstance(record.replacement_candidate_size, bool) or record.replacement_candidate_size <= 0:
                raise ValueError("replacement candidate size must be a positive integer")
            if not isinstance(record.replacement_candidate_quality, dict) or not record.replacement_candidate_quality:
                raise ValueError("replacement candidate quality must be a non-empty object")
        if record.manual_import_command_id is not None and (
            not isinstance(record.manual_import_command_id, int)
            or isinstance(record.manual_import_command_id, bool)
            or record.manual_import_command_id <= 0
        ):
            raise ValueError("manual import command ID must be a positive integer")
        for timestamp in (
            record.manual_import_submitted_at, record.replacement_verified_at,
        ):
            if timestamp is not None:
                if not isinstance(timestamp, str) or datetime.fromisoformat(timestamp).tzinfo is None:
                    raise ValueError("operation timestamps must include a timezone")
        verified_values = (
            record.replacement_verified_at,
            record.final_replacement_movie_file_id,
            record.final_replacement_path,
            record.final_replacement_size,
            record.final_replacement_quality,
        )
        has_verified_value = any(value is not None for value in verified_values)
        if has_verified_value != (record.state == "replacement_verified"):
            raise ValueError("verified replacement data and state must be persisted together")
        if has_verified_value:
            if not all(value is not None for value in verified_values):
                raise ValueError("verified replacement identity must be complete")
            if (
                not isinstance(record.final_replacement_movie_file_id, int)
                or isinstance(record.final_replacement_movie_file_id, bool)
                or record.final_replacement_movie_file_id <= 0
                or record.final_replacement_movie_file_id == record.original_movie_file_id
            ):
                raise ValueError("verified movie file ID must differ from the original")
            if (
                not isinstance(record.final_replacement_path, str)
                or not record.final_replacement_path.strip()
                or not PurePosixPath(record.final_replacement_path).is_absolute()
                or record.final_replacement_path == record.original_file_path
            ):
                raise ValueError("verified replacement path must differ from the original")
            if (
                not isinstance(record.final_replacement_size, int)
                or isinstance(record.final_replacement_size, bool)
                or record.final_replacement_size <= 0
                or record.final_replacement_size != record.replacement_candidate_size
                or record.final_replacement_size >= record.original_file_size
            ):
                raise ValueError("verified replacement size is inconsistent")
            if not isinstance(record.final_replacement_quality, dict) or not record.final_replacement_quality:
                raise ValueError("verified replacement quality must be a non-empty object")
            candidate_quality_name = cls._quality_name(record.replacement_candidate_quality)
            if (
                candidate_quality_name is None
                or cls._quality_name(record.final_replacement_quality) != candidate_quality_name
            ):
                raise ValueError("verified replacement quality does not match the candidate")
        return record

    @staticmethod
    def _quality_name(quality):
        if not isinstance(quality, dict):
            return None
        nested = quality.get("quality")
        name = nested.get("name") if isinstance(nested, dict) else quality.get("name")
        return name.strip().casefold() if isinstance(name, str) and name.strip() else None
