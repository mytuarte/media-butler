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
from services.radarr_service import RadarrService


class MediaAttentionService:
    """Tracks movie pipeline progress without creating user-facing alerts."""

    ACTIVE_REQUEST_STATUSES = {1, 2}

    def __init__(
        self,
        state_store: MediaAttentionStateStore | None = None,
        overseerr: OverseerrService | None = None,
        radarr: RadarrService | None = None,
        tmdb: TmdbService | None = None,
    ):
        self.state_store = state_store or MediaAttentionStateStore()
        self.overseerr = overseerr or OverseerrService()
        self.radarr = radarr or RadarrService()
        self.tmdb = tmdb or TmdbService()
        self.tracked_media = self.state_store.load()

    def evaluate_requested_movies(
        self,
        now: datetime | None = None,
    ) -> list[PipelineSnapshot]:
        """Capture and evaluate all eligible movie requests for this cycle."""
        now = now or datetime.now(timezone.utc)
        requests = self.overseerr.get_requests().get("results", [])
        movies_by_tmdb = {
            movie.get("tmdbId"): movie
            for movie in self.radarr.get_movies()
            if movie.get("tmdbId") is not None
        }
        snapshots = []

        for request in requests:
            if not self._is_active_movie_request(request):
                continue

            tmdb_id = request["media"]["tmdbId"]
            if not self.tmdb.movie_has_digital_availability(tmdb_id):
                continue

            snapshot = self.capture_movie_snapshot(
                request,
                movies_by_tmdb.get(tmdb_id),
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
    ) -> PipelineSnapshot:
        """Build a deterministic movie snapshot from currently available evidence."""
        media = request["media"]
        tmdb_id = media["tmdbId"]
        title = media.get("title") or request.get("title") or "Unknown Movie"
        arr_evidence = self._movie_arr_evidence(movie)
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
    def _movie_arr_evidence(movie: dict | None) -> dict:
        if movie is None:
            return {"present": False}

        return {
            "present": True,
            "id": movie.get("id"),
            "has_file": movie.get("hasFile", False),
            "monitored": movie.get("monitored", False),
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
