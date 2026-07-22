import asyncio
from datetime import datetime, timedelta, timezone

from config import Config
from models.media_attention import MediaAttentionAlert, PipelineSnapshot, PipelineStage
from services.log_service import logger
from services.media_attention_alert_store import MediaAttentionAlertStore
from services.media_attention_service import MediaAttentionService


class MediaAttentionMonitorService:
    """Periodically identifies stalled, digitally available requested movies."""

    STALL_THRESHOLD = timedelta(minutes=20)
    TERMINAL_STAGES = {PipelineStage.PLEX_AVAILABLE}

    def __init__(
        self,
        attention_service: MediaAttentionService | None = None,
        alert_store: MediaAttentionAlertStore | None = None,
        discord_service=None,
        interval_seconds: float | None = None,
    ):
        self.attention_service = attention_service or MediaAttentionService()
        self.alert_store = alert_store or MediaAttentionAlertStore()
        self.discord = discord_service
        self.alerts = self.alert_store.load()
        self.interval_seconds = interval_seconds or Config.MEDIA_ATTENTION_INTERVAL_SECONDS
        self.stall_threshold = timedelta(minutes=Config.MEDIA_ATTENTION_STALL_MINUTES)
        self.running = False
        self._task = None

    def start(self) -> bool:
        if self.running:
            return False
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        return True

    async def _monitor_loop(self):
        while self.running:
            try:
                await self.run_cycle()
            except Exception:
                logger.exception("Media Attention monitoring cycle failed")
            await asyncio.sleep(self.interval_seconds)

    async def run_cycle(self, now: datetime | None = None) -> list[PipelineSnapshot]:
        now = now or datetime.now(timezone.utc)
        snapshots = self.attention_service.evaluate_requested_movies(now)
        for snapshot in snapshots:
            await self._evaluate_snapshot(snapshot, now)
        self.alert_store.save(self.alerts)
        active_count = sum(alert.status == "active" for alert in self.alerts.values())
        logger.info(
            "Media Attention cycle: movies checked=%s eligible=%s active attention=%s",
            self.attention_service.last_requests_checked,
            len(snapshots), active_count,
        )
        return snapshots

    async def _evaluate_snapshot(self, snapshot: PipelineSnapshot, now: datetime) -> None:
        tracked = self.attention_service.tracked_media[snapshot.media_key]
        active = self._active_alert(snapshot.media_key)
        elapsed = now - tracked.last_progress_at
        needs_attention = (
            snapshot.stage not in self.TERMINAL_STAGES and elapsed >= self.stall_threshold
        )
        logger.info(
            "Media Attention movie=%s stage=%s progress=%s last_progress=%s minutes needs_attention=%s",
            snapshot.title, snapshot.stage.name, snapshot.sab_evidence.get("percent"),
            int(elapsed.total_seconds() // 60), needs_attention,
        )

        if active and (not needs_attention or active.stage != snapshot.stage):
            active.status = "resolved"
            active.resolved_at = now
            logger.info("Media Attention resolved alert %s for %s", active.media_key, snapshot.title)
            active = None

        if not needs_attention:
            return

        stuck_minutes = int(elapsed.total_seconds() // 60)
        if active is None:
            tracked.stall_generation += 1
            key = f"{snapshot.media_key}:stall:{tracked.stall_generation}"
            active = MediaAttentionAlert(
                media_key=snapshot.media_key, media_type=snapshot.media_type,
                tmdb_id=snapshot.tmdb_id, request_id=snapshot.request_id,
                title=snapshot.title, stage=snapshot.stage, status="active",
                created_at=now, details_fingerprint=snapshot.progress_fingerprint,
            )
            self.alerts[key] = active
            await self._send_alert(active, snapshot, stuck_minutes)
            logger.info("Media Attention created alert %s for %s", key, snapshot.title)
        else:
            active.title = snapshot.title
            active.request_id = snapshot.request_id
            active.details_fingerprint = snapshot.progress_fingerprint
            await self._update_alert(active, snapshot, stuck_minutes)

    def _active_alert(self, media_key: str) -> MediaAttentionAlert | None:
        return next((alert for alert in self.alerts.values()
                     if alert.media_key == media_key and alert.status == "active"), None)

    async def _send_alert(self, alert, snapshot, stuck_minutes: int) -> None:
        if self.discord is None:
            return
        message = await self.discord.send_media_attention_alert(alert, snapshot, stuck_minutes)
        alert.message_id = message.id

    async def _update_alert(self, alert, snapshot, stuck_minutes: int) -> None:
        if self.discord is None or alert.message_id is None:
            return
        exists = await self.discord.update_media_attention_alert(
            alert.message_id, alert, snapshot, stuck_minutes
        )
        if exists is False:
            await self._send_alert(alert, snapshot, stuck_minutes)
