from dataclasses import dataclass


@dataclass
class MovieNotification:
    title: str
    year: int
    requester: str
    quality: str
    status: str = "Download Complete"