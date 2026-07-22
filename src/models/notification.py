from dataclasses import dataclass


@dataclass
class MovieNotification:
    title: str
    year: int
    requester: str | int | None
    quality: str
    status: str = "Download Complete"
