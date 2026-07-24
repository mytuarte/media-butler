"""Series-level Sonarr completion notifications."""
import asyncio
import hashlib
from datetime import datetime, timezone

from models.series_completion_notification import SeriesCompletionNotification
from services.log_service import logger
from services.series_completion_notification_state_store import SeriesCompletionNotificationStateStore
from services.series_progress_service import SeriesProgressService


class SeriesCompletionNotificationService:
    def __init__(self, sonarr, overseerr, notification_service, state_store=None):
        self.sonarr = sonarr
        self.overseerr = overseerr
        self.notification_service = notification_service
        self.progress_service = SeriesProgressService(sonarr)
        self.state_store = state_store or SeriesCompletionNotificationStateStore()
        self.state = self.state_store.load()
        self._lock = asyncio.Lock()

    @staticmethod
    def ignore_reason(payload: dict) -> str | None:
        event_type = str(payload.get("eventType") or "").lower()
        if event_type != "download":
            return f"event type '{payload.get('eventType') or 'missing'}' is not an episode download"
        if payload.get("isUpgrade") is True or (isinstance(payload.get("episodeFile"), dict) and payload["episodeFile"].get("isUpgrade") is True):
            return "download is a quality upgrade"
        if not isinstance(payload.get("episodes"), list) or not payload["episodes"]:
            return "download has no imported episodes"
        return None

    async def process(self, payload: dict) -> bool:
        reason = self.ignore_reason(payload)
        if reason:
            logger.info("Ignoring Sonarr webhook: %s", reason)
            return False
        series_id = self._series_id(payload)
        if series_id is None:
            logger.info("Ignoring Sonarr download: missing stable Sonarr series ID.")
            return False
        async with self._lock:
            prepared = await asyncio.to_thread(self._prepare, series_id)
            if prepared is None:
                return False
            key, signature, released_keys, series, progress = prepared
            if self.state.get(key, {}).get("signature") == signature:
                logger.info("Sonarr series %s completion was already notified.", series_id)
                return False
            request = await asyncio.to_thread(self.overseerr.get_request, series["tmdbId"], refresh=True)
            name = request.requester if request is not None else None
            discord_id = request.requester_discord_id if request is not None and self._valid_discord_id(request.requester_discord_id) else None
            notification = SeriesCompletionNotification(series.get("title") or "Unknown Series", series.get("year") if isinstance(series.get("year"), int) else None, name, discord_id, len(progress.arr_imported_episode_keys), len(progress.released_episode_keys))
            await self.notification_service.send_series_completion_notification(notification)
            candidate = dict(self.state)
            candidate[key] = {"released_episode_keys": list(released_keys), "signature": signature, "notified_at": datetime.now(timezone.utc).isoformat()}
            try:
                await asyncio.to_thread(self.state_store.save, candidate)
            except Exception:
                logger.exception("Failed to persist Sonarr completion notification state.")
                raise
            self.state = candidate
            logger.info("Sonarr series completion notification sent for %s.", notification.title)
            return True

    def _prepare(self, series_id: int):
        series = self._resolve_series(series_id)
        if series is None:
            logger.info("Ignoring Sonarr download: series %s could not be resolved.", series_id); return None
        tmdb_id = series.get("tmdbId")
        if not isinstance(tmdb_id, int):
            logger.info("Ignoring Sonarr download: series %s has no TMDb ID.", series_id); return None
        progress = self.progress_service.evaluate(series_id, datetime.now(timezone.utc))
        if not progress.caught_up:
            logger.info("Sonarr series %s is not caught up; no notification sent.", series_id); return None
        return f"tv:tmdb:{tmdb_id}", self._signature(progress.released_episode_keys), progress.released_episode_keys, series, progress

    def _resolve_series(self, series_id: int) -> dict | None:
        return self.sonarr.get_series_by_id(series_id)

    @staticmethod
    def _valid_discord_id(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @staticmethod
    def _series_id(payload: dict) -> int | None:
        value = payload.get("seriesId", payload.get("series", {}).get("id") if isinstance(payload.get("series"), dict) else None)
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None

    @staticmethod
    def _signature(keys: tuple[str, ...]) -> str:
        return hashlib.sha256("\n".join(keys).encode()).hexdigest()
