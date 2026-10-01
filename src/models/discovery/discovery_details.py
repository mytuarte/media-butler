from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryDetails:
    """TMDB details shown when a discovery item is selected in Discord."""

    title: str
    media_type: str
    tmdb_id: int
    overview: str | None = None
    vote_average: float | None = None
    vote_count: int | None = None
    poster_url: str | None = None
    release_date: str | None = None
    streaming_providers: tuple[str, ...] = ()
