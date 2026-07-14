from dataclasses import dataclass


@dataclass
class DiscoveryItem:
    title: str
    media_type: str

    release_date: str | None = None
    poster_url: str | None = None
    overview: str | None = None

    in_library: bool = False
    requested: bool = False
    requester: str | None = None