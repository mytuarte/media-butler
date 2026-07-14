from dataclasses import dataclass


@dataclass
class TrendingItem:
    tmdb_id: int

    title: str
    media_type: str

    rank: int

    release_date: str | None = None
    overview: str | None = None
    poster_path: str | None = None

    in_library: bool = False
    requested: bool = False
    requester: str | None = None