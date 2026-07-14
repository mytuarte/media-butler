from dataclasses import dataclass, field

from models.space_item import SpaceItem


@dataclass
class SpaceResult:
    # NAS
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0

    # Managed Media
    movie_count: int = 0
    series_count: int = 0

    movie_bytes: int = 0
    series_bytes: int = 0

    # Largest Media
    largest_movies: list[SpaceItem] = field(
        default_factory=list
    )

    largest_series: list[SpaceItem] = field(
        default_factory=list
    )