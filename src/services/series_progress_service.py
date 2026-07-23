"""Reusable, live Sonarr series completion evaluation."""
from datetime import datetime, timezone

from models.media_attention import EpisodeProgress


class SeriesProgressService:
    def __init__(self, sonarr):
        self.sonarr = sonarr

    def evaluate(self, series_id: int, now: datetime | None = None) -> EpisodeProgress:
        now = now or datetime.now(timezone.utc)
        released, imported = [], []
        # A progress decision must never be based on Sonarr's indefinite cache.
        for episode in self.sonarr.get_episodes(series_id, refresh=True):
            if episode.get("seasonNumber") == 0 or not self._released(episode, now):
                continue
            key = self.episode_key(episode)
            released.append(key)
            if episode.get("hasFile") is True:
                imported.append(key)
        return EpisodeProgress(tuple(sorted(released)), tuple(sorted(imported)))

    @staticmethod
    def episode_key(episode: dict) -> str:
        return f"S{int(episode['seasonNumber']):02d}E{int(episode['episodeNumber']):02d}"

    @staticmethod
    def _released(episode: dict, now: datetime) -> bool:
        value = episode.get("airDateUtc") or episode.get("airDate")
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed <= now
        except (TypeError, ValueError):
            return False
