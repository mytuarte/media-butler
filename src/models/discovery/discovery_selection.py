from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverySelection:
    """The small amount of dashboard data needed to rebuild a select menu."""

    title: str
    media_type: str
    tmdb_id: int
    status_icon: str
    release_status: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "DiscoverySelection":
        if not isinstance(data, dict):
            raise ValueError("Discovery selection must be an object.")

        title = data["title"]
        media_type = data["media_type"]
        tmdb_id = data["tmdb_id"]
        status_icon = data["status_icon"]
        release_status = data.get("release_status")

        if not isinstance(title, str) or not title.strip():
            raise ValueError("Discovery selection title must be a non-empty string.")

        if media_type not in {"movie", "tv"}:
            raise ValueError("Discovery selection media type is invalid.")

        if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool) or tmdb_id <= 0:
            raise ValueError("Discovery selection TMDB ID must be positive.")

        if not isinstance(status_icon, str) or not status_icon:
            raise ValueError("Discovery selection status icon must be a string.")

        if release_status is not None and not isinstance(release_status, str):
            raise ValueError("Discovery selection release status must be a string.")

        return cls(
            title=title,
            media_type=media_type,
            tmdb_id=tmdb_id,
            status_icon=status_icon,
            release_status=release_status,
        )

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "media_type": self.media_type,
            "tmdb_id": self.tmdb_id,
            "status_icon": self.status_icon,
            "release_status": self.release_status,
        }
