from datetime import datetime, timezone

from models.media_attention import (
    MediaAttentionMediaType,
    PipelineSnapshot,
    PipelineStage,
    TrackedMedia,
)
from services.discovery.tmdb_service import TmdbService
from services.media_attention_state_store import MediaAttentionStateStore
from services.overseerr_service import OverseerrService
from services.plex_service import PlexService
from services.radarr_service import RadarrService
from services.sabnzbd_client import SabnzbdClient


class MediaAttentionService:
    """Tracks movie pipeline progress without creating user-facing alerts."""

    ACTIVE_REQUEST_STATUSES = {1, 2}

    def __init__(
        self,
        state_store: MediaAttentionStateStore | None = None,
        overseerr: OverseerrService | None = None,
        radarr: RadarrService | None = None,
        tmdb: TmdbService | None = None,
        sabnzbd: SabnzbdClient | None = None,
        plex: PlexService | None = None,
    ):
        self.state_store = state_store or MediaAttentionStateStore()
        self.overseerr = overseerr or OverseerrService()
        self.radarr = radarr or RadarrService()
        self.tmdb = tmdb or TmdbService()
        self.sabnzbd = sabnzbd or SabnzbdClient()
        self.plex = plex or PlexService()
        self.tracked_media = self.state_store.load()
        self.last_requests_checked = 0

    def evaluate_requested_movies(
        self,
        now: datetime | None = None,
    ) -> list[PipelineSnapshot]:
        """Capture and evaluate all eligible movie requests for this cycle."""
        now = now or datetime.now(timezone.utc)
        requests = self.overseerr.get_requests().get("results", [])
        self.last_requests_checked = len(requests)
        movies_by_tmdb = {
            movie.get("tmdbId"): movie
            for movie in self.radarr.get_movies()
            if movie.get("tmdbId") is not None
        }
        radarr_history = None
        sab_queue = None
        sab_history = None
        snapshots = []

        for request in requests:
            if not self._is_active_movie_request(request):
                continue

            tmdb_id = request["media"]["tmdbId"]
            if not self.tmdb.movie_has_digital_availability(tmdb_id):
                continue

            if radarr_history is None:
                radarr_history = self.radarr.get_history().get("records", [])
                sab_queue = self.sabnzbd.get_queue().get("queue", {}).get(
                    "slots", []
                )
                sab_history = self.sabnzbd.get_history().get("history", {}).get(
                    "slots", []
                )

            media = request["media"]

            snapshot = self.capture_movie_snapshot(
                request,
                movies_by_tmdb.get(tmdb_id),
                sab_evidence=self._movie_sab_evidence(
                    media.get("title") or request.get("title") or "",
                    sab_queue,
                    sab_history or [],
                ),
                plex_evidence={
                    "available": self.plex.movie_is_available(
                        tmdb_id,
                        media.get("title") or request.get("title") or "",
                    )
                },
                history=self._movie_history_evidence(
                    movies_by_tmdb.get(tmdb_id), radarr_history or []
                ),
            )
            self.evaluate_snapshot(snapshot, now)
            snapshots.append(snapshot)

        if snapshots:
            self.state_store.save(self.tracked_media)

        return snapshots

    def capture_movie_snapshot(
        self,
        request: dict,
        movie: dict | None,
        sab_evidence: dict | None = None,
        plex_evidence: dict | None = None,
        history: list[dict] | None = None,
    ) -> PipelineSnapshot:
        """Build a deterministic movie snapshot from currently available evidence."""
        media = request["media"]
        tmdb_id = media["tmdbId"]
        title = media.get("title") or request.get("title") or "Unknown Movie"
        arr_evidence = self._movie_arr_evidence(movie, history)
        sab_evidence = sab_evidence or {}
        plex_evidence = plex_evidence or {}
        stage, detail = self._resolve_movie_stage(
            movie,
            sab_evidence,
            plex_evidence,
        )

        return PipelineSnapshot(
            media_key=self.movie_key(tmdb_id),
            media_type=MediaAttentionMediaType.MOVIE,
            tmdb_id=tmdb_id,
            request_id=request["id"],
            title=title,
            stage=stage,
            stage_detail=detail,
            arr_evidence=arr_evidence,
            sab_evidence=sab_evidence,
            plex_evidence=plex_evidence,
        )

    def evaluate_snapshot(
        self,
        snapshot: PipelineSnapshot,
        now: datetime,
    ) -> bool:
        """Record a snapshot and return whether it represents pipeline progress."""
        tracked = self.tracked_media.get(snapshot.media_key)

        if tracked is None:
            self.tracked_media[snapshot.media_key] = TrackedMedia(
                media_key=snapshot.media_key,
                media_type=snapshot.media_type,
                tmdb_id=snapshot.tmdb_id,
                request_id=snapshot.request_id,
                title=snapshot.title,
                current_stage=snapshot.stage,
                previous_stage=None,
                last_progress_at=now,
                last_progress_fingerprint=snapshot.progress_fingerprint,
            )
            return True

        progress_detected = (
            tracked.last_progress_fingerprint != snapshot.progress_fingerprint
        )
        previous_stage = tracked.current_stage
        tracked.current_stage = snapshot.stage
        tracked.request_id = snapshot.request_id
        tracked.title = snapshot.title

        if progress_detected:
            tracked.previous_stage = previous_stage
            tracked.last_progress_at = now
            tracked.last_progress_fingerprint = snapshot.progress_fingerprint

        return progress_detected

    @classmethod
    def movie_key(cls, tmdb_id: int) -> str:
        return f"movie:tmdb:{tmdb_id}"

    def _is_active_movie_request(self, request: dict) -> bool:
        media = request.get("media", {})
        return (
            request.get("type") == "movie"
            and request.get("status") in self.ACTIVE_REQUEST_STATUSES
            and media.get("tmdbId") is not None
        )

    @staticmethod
    def _movie_arr_evidence(
        movie: dict | None,
        history: list[dict] | None = None,
    ) -> dict:
        if movie is None:
            return {"present": False}

        evidence = {
            "present": True,
            "id": movie.get("id"),
            "has_file": movie.get("hasFile", False),
            "monitored": movie.get("monitored", False),
        }
        if history is not None:
            evidence["history"] = history
        return evidence

    @classmethod
    def _movie_history_evidence(
        cls,
        movie: dict | None,
        records: list[dict],
    ) -> list[dict]:
        if movie is None or movie.get("id") is None:
            return []
        relevant = [
            record for record in records if record.get("movieId") == movie["id"]
        ]
        return [
            {
                "event_type": record.get("eventType"),
                "date": record.get("date"),
                "download_id": record.get("data", {}).get("downloadId"),
            }
            for record in relevant[:10]
        ]

    @classmethod
    def _movie_sab_evidence(
        cls, title: str, queue_slots: list[dict], history_slots: list[dict]
    ) -> dict:
        active = cls._find_sab_slot(title, queue_slots)
        if active is not None:
            return cls._sab_slot_evidence(active, active=True, completed=False)

        completed = cls._find_sab_slot(title, history_slots)
        if completed is not None and str(completed.get("status", "")).lower() in {
            "completed",
            "complete",
        }:
            return cls._sab_slot_evidence(completed, active=False, completed=True)
        return {"active": False, "completed": False}

    @staticmethod
    def _find_sab_slot(title: str, slots: list[dict]) -> dict | None:
        normalized_title = SabnzbdClient._normalize(title)
        if not normalized_title:
            return None
        return next(
            (
                slot
                for slot in slots
                if normalized_title
                in SabnzbdClient._normalize(
                    slot.get("filename") or slot.get("name") or ""
                )
            ),
            None,
        )

    @staticmethod
    def _sab_slot_evidence(slot: dict, active: bool, completed: bool) -> dict:
        return {
            "active": active,
            "completed": completed,
            "download_id": slot.get("nzo_id") or slot.get("id"),
            "status": slot.get("status"),
            "percent": slot.get("percentage"),
            "size": slot.get("mb") or slot.get("size"),
            "size_left": slot.get("mbleft") or slot.get("sizeleft"),
        }

    @staticmethod
    def _resolve_movie_stage(
        movie: dict | None,
        sab_evidence: dict,
        plex_evidence: dict,
    ) -> tuple[PipelineStage, str]:
        if plex_evidence.get("available") is True:
            return PipelineStage.PLEX_AVAILABLE, "Available in Plex."

        if movie is None:
            return PipelineStage.WAITING_FOR_ARR, "Waiting for Radarr."

        if movie.get("hasFile"):
            return PipelineStage.PLEX_SYNC_PENDING, "Imported; waiting for Plex."

        if sab_evidence.get("active") is True:
            return PipelineStage.DOWNLOADING, "Downloading."

        if sab_evidence.get("completed") is True:
            return PipelineStage.IMPORT_PENDING, "Waiting for Radarr import."

        return PipelineStage.ARR_SEARCHING, "Waiting for Radarr search activity."
