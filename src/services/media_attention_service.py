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
from services.sonarr_service import SonarrService
from services.series_progress_service import SeriesProgressService
from services.log_service import logger


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
        sonarr: SonarrService | None = None,
    ):
        self.state_store = state_store or MediaAttentionStateStore()
        self.overseerr = overseerr or OverseerrService()
        self.radarr = radarr or RadarrService()
        self.tmdb = tmdb or TmdbService()
        self.sabnzbd = sabnzbd or SabnzbdClient()
        self.plex = plex or PlexService()
        self.sonarr = sonarr or SonarrService()
        self.series_progress = SeriesProgressService(self.sonarr)
        self.tracked_media = self.state_store.load()
        self.last_requests_checked = 0

    def evaluate_requested_movies(
        self,
        now: datetime | None = None,
    ) -> list[PipelineSnapshot]:
        """Capture and evaluate all eligible movie requests for this cycle."""
        now = now or datetime.now(timezone.utc)

        try:
            self.plex.test_connection()
        except Exception as error:
            logger.warning(
                "Plex unavailable, skipping availability evaluation: %s", error
            )
            self.last_requests_checked = 0
            return []

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

            movie = movies_by_tmdb.get(tmdb_id)
            title = self._movie_title(request, movie)

            snapshot = self.capture_movie_snapshot(
                request,
                movie,
                title=title,
                sab_evidence=self._movie_sab_evidence(
                    title,
                    sab_queue,
                    sab_history or [],
                ),
                plex_evidence={
                    "available": self.plex.movie_is_available(tmdb_id, title)
                },
                history=self._movie_history_evidence(movie, radarr_history or []),
            )
            self.evaluate_snapshot(snapshot, now)
            snapshots.append(snapshot)

        if snapshots:
            self.state_store.save(self.tracked_media)

        return snapshots

    def evaluate_requested_tv(self, now: datetime | None = None) -> list[PipelineSnapshot]:
        """Evaluate each active TV request once, at series rather than episode scope."""
        now = now or datetime.now(timezone.utc)
        requests = self.overseerr.get_requests().get("results", [])
        tv_requests = self._deduplicate_tv_requests(requests)
        if not tv_requests:
            return []
        series_by_tmdb = {item.get("tmdbId"): item for item in self.sonarr.get_series()
                          if item.get("tmdbId") is not None}
        queue = None
        snapshots = []
        for request in tv_requests:
            tmdb_id = request["media"]["tmdbId"]
            series = series_by_tmdb.get(tmdb_id)
            if series is None and not self.tmdb.tv_has_digital_availability(tmdb_id):
                continue
            title = request["media"].get("title") or request.get("title") or (series or {}).get("title") or "Unknown Series"
            progress = None
            evidence = {"present": series is not None}
            queue_evidence = {"active": False, "completed": False, "records": []}
            if series is not None:
                progress = self.series_progress.evaluate(series["id"], now)
                if not progress.released_episode_keys:
                    continue
                if queue is None:
                    queue = self.sonarr.get_queue()
                queue_evidence = self._series_queue_evidence(series["id"], queue)
                evidence.update({"id": series["id"]})
            stage, detail = self._resolve_tv_stage(series, progress, queue_evidence)
            snapshot = PipelineSnapshot(media_key=self.tv_key(tmdb_id), media_type=MediaAttentionMediaType.TV,
                tmdb_id=tmdb_id, request_id=request["id"], title=title, stage=stage, stage_detail=detail,
                arr_evidence=evidence, sab_evidence=queue_evidence, episode_progress=progress)
            self.evaluate_snapshot(snapshot, now)
            snapshots.append(snapshot)
        if snapshots:
            self.state_store.save(self.tracked_media)
        return snapshots

    def capture_movie_snapshot(
        self,
        request: dict,
        movie: dict | None,
        title: str | None = None,
        sab_evidence: dict | None = None,
        plex_evidence: dict | None = None,
        history: list[dict] | None = None,
    ) -> PipelineSnapshot:
        """Build a deterministic movie snapshot from currently available evidence."""
        media = request["media"]
        tmdb_id = media["tmdbId"]
        title = title or self._movie_title(request, movie)
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
                first_seen_at=now,
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

    @staticmethod
    def _movie_title(request: dict, movie: dict | None) -> str:
        media = request.get("media", {})
        return (
            media.get("title")
            or request.get("title")
            or (movie or {}).get("title")
            or "Unknown Movie"
        )

    @classmethod
    def movie_key(cls, tmdb_id: int) -> str:
        return f"movie:tmdb:{tmdb_id}"

    @classmethod
    def tv_key(cls, tmdb_id: int) -> str:
        return f"tv:tmdb:{tmdb_id}"

    def _is_active_movie_request(self, request: dict) -> bool:
        media = request.get("media", {})
        return (
            request.get("type") == "movie"
            and request.get("status") in self.ACTIVE_REQUEST_STATUSES
            and media.get("tmdbId") is not None
        )

    @staticmethod
    def _is_active_tv_request(request: dict) -> bool:
        media = request.get("media", {})
        return request.get("type") == "tv" and request.get("status") in MediaAttentionService.ACTIVE_REQUEST_STATUSES and media.get("tmdbId") is not None

    @classmethod
    def _deduplicate_tv_requests(cls, requests: list[dict]) -> list[dict]:
        """Keep the newest request per series; ID is a stable fallback."""
        selected = {}
        for request in requests:
            if not cls._is_active_tv_request(request):
                continue
            key = request["media"]["tmdbId"]
            def request_id(item):
                try:
                    return int(item.get("id"))
                except (TypeError, ValueError):
                    return -1

            def rank(item):
                value = item.get("createdAt")
                try:
                    created = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    return (1, created.timestamp(), request_id(item))
                except (TypeError, ValueError):
                    return (0, 0, request_id(item))
            if key not in selected or rank(request) > rank(selected[key]):
                selected[key] = request
        return [selected[key] for key in sorted(selected)]

    @staticmethod
    def _series_queue_evidence(series_id: int, records: list[dict]) -> dict:
        def identifier(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def number(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def state(value):
            return "".join(character for character in str(value or "").lower() if character.isalnum())

        relevant = []
        for record in records:
            if not isinstance(record, dict):
                continue
            series = record.get("series") if isinstance(record.get("series"), dict) else {}
            record_series_id = identifier(record.get("seriesId") if record.get("seriesId") is not None else series.get("id"))
            if record_series_id != identifier(series_id):
                continue
            total, remaining = number(record.get("size")), number(record.get("sizeleft"))
            percent = number(record.get("progress"))
            if percent is None and total and remaining is not None:
                percent = round((1 - float(remaining) / float(total)) * 100, 2)
            episode_values = record.get("episodeIds")
            episode_ids = list(episode_values) if isinstance(episode_values, (list, tuple)) else []
            episode_ids += [record.get("episodeId")]
            episode = record.get("episode") if isinstance(record.get("episode"), dict) else {}
            episode_ids += [episode.get("id")]
            episode_ids = sorted({item for value in episode_ids if (item := identifier(value)) is not None})
            relevant.append({"download_id": record.get("downloadId"), "status": state(record.get("status")),
                "tracked_state": state(record.get("trackedDownloadState") or record.get("trackedDownloadStatus")),
                "episode_ids": episode_ids, "size": total, "size_left": remaining, "percent": percent})
        active_states = {"downloading", "queued", "paused", "warning"}
        import_states = {"completed", "importpending", "importing", "awaitingimport"}
        relevant.sort(key=lambda item: (str(item["download_id"]), item["episode_ids"], item["status"], item["tracked_state"]))
        states = [{item["status"], item["tracked_state"]} for item in relevant]
        active = any(active_states & state for state in states)
        completed = any(import_states & state for state in states)
        priority = active_states, import_states
        representative = next((item for stateset in priority for item in relevant if stateset & {item["status"], item["tracked_state"]}), relevant[0] if relevant else {})
        representative_states = {representative.get("status", ""), representative.get("tracked_state", "")}
        effective_status = next((candidate for stateset in priority for candidate in (representative.get("status"), representative.get("tracked_state")) if candidate in stateset and candidate in representative_states), representative.get("status"))
        return {"active": active, "completed": completed, "records": relevant,
                "status": effective_status, "percent": representative.get("percent")}

    @staticmethod
    def _resolve_tv_stage(series, progress, queue):
        if series is None:
            return PipelineStage.WAITING_FOR_SONARR, "Waiting for Sonarr."
        if progress and progress.caught_up:
            return PipelineStage.SERIES_CAUGHT_UP, "Every released episode is imported."
        if queue.get("active"):
            return PipelineStage.DOWNLOADING, "Sonarr download in progress."
        if queue.get("completed"):
            return PipelineStage.IMPORT_PENDING, "Waiting for Sonarr import."
        return PipelineStage.SONARR_SEARCHING, "Waiting for Sonarr search activity."

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
