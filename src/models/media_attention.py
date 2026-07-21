from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MediaAttentionMediaType(Enum):
    MOVIE = "movie"
    TV = "tv"


class PipelineStage(Enum):
    WAITING_FOR_ARR = "waiting_for_arr"
    ARR_SEARCHING = "arr_searching"
    DOWNLOADING = "downloading"
    IMPORT_PENDING = "import_pending"
    PLEX_SYNC_PENDING = "plex_sync_pending"
    PLEX_AVAILABLE = "plex_available"


@dataclass(frozen=True)
class EpisodeProgress:
    released_episode_keys: tuple[str, ...] = ()
    arr_imported_episode_keys: tuple[str, ...] = ()
    plex_episode_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "released_episode_keys": list(self.released_episode_keys),
            "arr_imported_episode_keys": list(self.arr_imported_episode_keys),
            "plex_episode_keys": list(self.plex_episode_keys),
        }


@dataclass(frozen=True)
class PipelineSnapshot:
    media_key: str
    media_type: MediaAttentionMediaType
    tmdb_id: int
    request_id: int
    title: str
    stage: PipelineStage
    stage_detail: str
    arr_evidence: dict = field(default_factory=dict)
    sab_evidence: dict = field(default_factory=dict)
    plex_evidence: dict = field(default_factory=dict)
    episode_progress: EpisodeProgress | None = None
    progress_fingerprint: str = field(init=False)

    def __post_init__(self):
        progress_data = {
            "stage": self.stage.value,
            "arr_evidence": self.arr_evidence,
            "sab_evidence": self.sab_evidence,
            "plex_evidence": self.plex_evidence,
            "episode_progress": (
                self.episode_progress.to_dict()
                if self.episode_progress is not None
                else None
            ),
        }
        serialized = json.dumps(
            progress_data,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
        object.__setattr__(self, "progress_fingerprint", fingerprint)


@dataclass
class TrackedMedia:
    media_key: str
    media_type: MediaAttentionMediaType
    tmdb_id: int
    request_id: int
    title: str
    current_stage: PipelineStage
    previous_stage: PipelineStage | None
    last_progress_at: datetime
    last_progress_fingerprint: str
    stall_generation: int = 0

    def to_dict(self) -> dict:
        return {
            "media_type": self.media_type.value,
            "tmdb_id": self.tmdb_id,
            "request_id": self.request_id,
            "title": self.title,
            "current_stage": self.current_stage.value,
            "previous_stage": (
                self.previous_stage.value if self.previous_stage is not None else None
            ),
            "last_progress_at": self.last_progress_at.isoformat(),
            "last_progress_fingerprint": self.last_progress_fingerprint,
            "stall_generation": self.stall_generation,
        }

    @classmethod
    def from_dict(cls, media_key: str, data: dict) -> "TrackedMedia":
        previous_stage = data.get("previous_stage")
        return cls(
            media_key=media_key,
            media_type=MediaAttentionMediaType(data["media_type"]),
            tmdb_id=data["tmdb_id"],
            request_id=data["request_id"],
            title=data["title"],
            current_stage=PipelineStage(data["current_stage"]),
            previous_stage=(PipelineStage(previous_stage) if previous_stage else None),
            last_progress_at=datetime.fromisoformat(data["last_progress_at"]),
            last_progress_fingerprint=data["last_progress_fingerprint"],
            stall_generation=data.get("stall_generation", 0),
        )
