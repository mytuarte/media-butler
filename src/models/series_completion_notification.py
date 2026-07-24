from dataclasses import dataclass


@dataclass(frozen=True)
class SeriesCompletionNotification:
    title: str
    year: int | None
    requester_name: str | None
    requester_discord_id: int | None
    downloaded_episodes: int
    released_episodes: int
    status: str = "All Released Episodes Downloaded"
