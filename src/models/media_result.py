from dataclasses import dataclass


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