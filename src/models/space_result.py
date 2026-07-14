from dataclasses import dataclass


@dataclass
class SpaceResult:
    movie_count: int = 0
    series_count: int = 0

    movie_size_bytes: int = 0
    series_size_bytes: int = 0