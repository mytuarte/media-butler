"""Normalized, read-only media analysis models."""
from dataclasses import dataclass, field

@dataclass
class MediaAnalysis:
    media_type: str
    title: str
    year: int | None
    total_size_bytes: int | None
    file_count: int
    known_size_file_count: int = 0
    unknown_size_file_count: int = 0
    quality_distribution: dict[str, int] = field(default_factory=dict)
    resolution_distribution: dict[str, int] = field(default_factory=dict)
    video_codec_distribution: dict[str, int] = field(default_factory=dict)
    audio_codec_distribution: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

@dataclass
class MovieAnalysis(MediaAnalysis):
    runtime_minutes: float | None = None
    size_bytes: int | None = None
    size_per_hour_bytes: float | None = None
    estimated_total_bitrate_mbps: float | None = None
    quality: str | None = None
    resolution: str | None = None
    video_codec: str | None = None
    video_dynamic_range: str | None = None
    audio_codec: str | None = None
    audio_channels: str | None = None
    audio_languages: list[str] = field(default_factory=list)
    file_relative_path: str | None = None
    original_release_name: str | None = None

@dataclass
class EpisodeFileAnalysis:
    season_number: int | None
    episode_number: int | None
    title: str | None
    size_bytes: int | None
    quality: str | None
    resolution: str | None
    video_codec: str | None
    audio_codec: str | None
    audio_channels: str | None
    file_relative_path: str | None
    physical_file_key: str = ""

@dataclass
class SeasonAnalysis:
    season_number: int
    file_count: int
    total_size_bytes: int | None
    average_file_size_bytes: float | None
    known_size_file_count: int = 0
    unknown_size_file_count: int = 0
    quality_distribution: dict[str, int] = field(default_factory=dict)
    resolution_distribution: dict[str, int] = field(default_factory=dict)
    video_codec_distribution: dict[str, int] = field(default_factory=dict)

@dataclass
class SeriesAnalysis(MediaAnalysis):
    series_id: int = 0
    total_episode_files: int = 0
    average_episode_size_bytes: float | None = None
    seasons: list[SeasonAnalysis] = field(default_factory=list)
    largest_episode_files: list[EpisodeFileAnalysis] = field(default_factory=list)
    released_episode_count: int = 0
    downloaded_released_episode_count: int = 0
    specials_file_count: int = 0
    specials_size_bytes: int | None = None
