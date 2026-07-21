from dataclasses import dataclass

from models.media_result import MediaResult


@dataclass
class MediaDetails:
    media: MediaResult

    size_bytes: int | None = None
    path: str | None = None
    added_date: str | None = None

    requester: str | None = None
    requested_date: str | None = None

    video_codec: str | None = None
    audio_codec: str | None = None
    resolution: str | None = None