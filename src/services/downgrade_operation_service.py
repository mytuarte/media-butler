"""Radarr replacement submission and read-only import-readiness inspection."""
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import requests

from models.downgrade import DowngradeOperation, DowngradeSuppression, ReplacementCandidate
from services.downgrade_operation_store import (
    DowngradeOperationStore,
    DowngradeOperationStoreError,
)
from services.downgrade_service import DowngradeService
from services.downgrade_suppression_store import DowngradeSuppressionStore
from services.log_service import logger


class ReleaseUnavailable(Exception):
    pass


class DuplicateDowngrade(Exception):
    pass


class RadarrRejected(Exception):
    pass


class UnsafeOriginalMovieFile(Exception):
    pass


@dataclass
class DowngradeOutcome:
    state: str
    downloader: str | None = None


@dataclass(frozen=True)
class ManualImportReadiness:
    state: str
    reason: str
    candidate: dict | None = None


class DowngradeOperationService:
    _active = set()
    _active_lock = threading.Lock()
    _APPROVED_REJECTION = "not an upgrade for existing movie file(s)"
    _STRUCTURED_REJECTION = re.compile(
        r"\Anot an upgrade for existing movie file\. existing quality: "
        r"(?P<existing>.+?)\. new quality (?P<new>.+?)\.\Z"
    )

    def __init__(
        self, radarr, suppression_store=None, discovery=None, timeout=75,
        poll_interval=3, operation_store=None,
    ):
        self.radarr = radarr
        self.suppressions = suppression_store or DowngradeSuppressionStore()
        self.discovery = discovery or DowngradeService(radarr=radarr)
        operation_path = getattr(self.suppressions, "state_file", None)
        if operation_store is None and isinstance(operation_path, Path):
            operation_store = DowngradeOperationStore(
                operation_path.parent / "downgrade_operations.json"
            )
        self.operations = (
            operation_store
            if operation_store is not None
            else DowngradeOperationStore()
        )
        self.timeout, self.poll_interval = timeout, poll_interval

    def run(self, movie_id: int, candidate: ReplacementCandidate, status=lambda value: None):
        self._validate_movie_id(movie_id)
        with self._active_lock:
            if (
                movie_id in self._active
                or self.suppressions.has_active(movie_id)
                or self.operations.get(movie_id) is not None
            ):
                raise DuplicateDowngrade()
            self._active.add(movie_id)
        try:
            raw_release = self.discovery.refresh_exact_movie_release(movie_id, candidate)
            if raw_release is None:
                raise ReleaseUnavailable()
            operation = self._new_operation(movie_id, candidate)
            self.operations.save(operation)  # Must be durable before either POST or suppression.
            record = DowngradeSuppression(
                movie_id, candidate.guid or "", candidate.release_name or "",
                candidate.indexer_id,
            )
            try:
                self.suppressions.add(record)  # Both records must be durable before POST.
            except Exception:
                try:
                    self.operations.remove(movie_id)
                except Exception:
                    logger.exception(
                        "Failed to roll back downgrade operation %s after suppression persistence failed",
                        movie_id,
                    )
                raise
            try:
                response = self.radarr.grab_release(raw_release)
            except requests.HTTPError as error:
                status_code = getattr(error.response, "status_code", None)
                if isinstance(status_code, int) and 400 <= status_code < 500:
                    self.suppressions.remove(movie_id)
                    self.operations.remove(movie_id)
                    raise RadarrRejected() from error
                self.operations.transition(movie_id, "ambiguous", "Release submission outcome is ambiguous")
                raise
            except (requests.Timeout, requests.ConnectionError):
                self.operations.transition(movie_id, "ambiguous", "Release submission outcome is ambiguous")
                raise
            download_id = response.get("downloadId") or response.get("downloadClientId")
            changes = {
                "state": "waiting_for_download",
                "last_safe_diagnostic_reason": "Release submitted; waiting for its exact download",
            }
            if download_id is not None and str(download_id).strip():
                changes["download_id"] = str(download_id)
            self.operations.update(movie_id, **changes)
            self.suppressions.update_download_id(movie_id, download_id)
            status("waiting")
            deadline = time.monotonic() + self.timeout
            queued_reported = False
            while time.monotonic() < deadline:
                item = self._matching_queue_item(movie_id, candidate, download_id, self.radarr.get_queue())
                if item:
                    found_id = item.get("downloadId") or item.get("downloadClientId")
                    self.suppressions.update_download_id(movie_id, found_id)
                    if found_id is not None and str(found_id).strip():
                        download_id = str(found_id)
                        self.operations.update(movie_id, download_id=download_id)
                    if self._downloading(item):
                        return DowngradeOutcome("downloading", item.get("downloadClient"))
                    if not queued_reported:
                        status("queued")
                        queued_reported = True
                time.sleep(self.poll_interval)
            return DowngradeOutcome("timeout")
        finally:
            with self._active_lock:
                self._active.discard(movie_id)

    def _new_operation(self, movie_id, candidate):
        try:
            snapshot = self.radarr.get_movie_file_snapshot(movie_id)
            snapshot_movie_id = snapshot["movie_id"]
            if (
                not isinstance(snapshot_movie_id, int)
                or isinstance(snapshot_movie_id, bool)
                or snapshot_movie_id <= 0
                or snapshot_movie_id != movie_id
            ):
                raise ValueError("snapshot movie ID does not exactly match")
            operation = DowngradeOperation(
                movie_id=snapshot_movie_id,
                selected_release_name=candidate.release_name,
                selected_release_guid=candidate.guid,
                selected_indexer_id=candidate.indexer_id,
                selected_release_size=candidate.size_bytes,
                selected_protocol=candidate.protocol,
                original_movie_file_id=snapshot["movie_file_id"],
                original_file_path=snapshot["path"],
                original_file_size=snapshot["size"],
                original_quality=snapshot.get("quality"),
            )
            return DowngradeOperation.from_dict(operation.to_dict())
        except (KeyError, TypeError, ValueError):
            raise UnsafeOriginalMovieFile() from None

    def inspect_manual_import_readiness(self, movie_id: int) -> ManualImportReadiness:
        self._validate_movie_id(movie_id)
        try:
            operation = self.operations.get(movie_id)
        except DowngradeOperationStoreError:
            return ManualImportReadiness(
                "ambiguous", "Persisted downgrade operation state cannot be trusted"
            )
        if operation is None:
            return ManualImportReadiness("blocked", "No persisted downgrade operation exists")
        if not operation.download_id:
            reason = "The exact download ID is unavailable; candidate lookup was not attempted"
            self.operations.transition(movie_id, "ambiguous", reason)
            return ManualImportReadiness("ambiguous", reason)

        self.operations.transition(movie_id, "inspecting_import", "Inspecting exact download candidates read-only")
        try:
            candidates = self.radarr.get_manual_import_candidates(operation.download_id, operation.movie_id)
        except (requests.RequestException, ValueError, TypeError):
            reason = "Radarr candidate inspection failed safely"
            self.operations.transition(movie_id, "ambiguous", reason)
            return ManualImportReadiness("ambiguous", reason)

        if not candidates:
            reason = "No manual-import candidates are available yet"
            self.operations.transition(movie_id, "inspecting_import", reason)
            return ManualImportReadiness("inspecting_import", reason)
        if len(candidates) != 1:
            return self._inspection_result(movie_id, "blocked", "Multiple candidates cannot be selected without guessing")

        candidate = candidates[0]
        unsafe_reason = self._candidate_safety_reason(candidate, operation)
        if unsafe_reason:
            return self._inspection_result(movie_id, "blocked", unsafe_reason)

        if "rejections" not in candidate:
            return self._inspection_result(movie_id, "blocked", "Candidate rejection data is missing or malformed")
        rejections = self._normalized_rejections(candidate.get("rejections"))
        if rejections is None:
            return self._inspection_result(movie_id, "blocked", "Candidate rejection data is missing or malformed")
        if not rejections:
            reason = "Safe candidate has no rejection; Radarr may be importing automatically"
            self.operations.transition(movie_id, "automatic_import_detected", reason)
            return ManualImportReadiness("automatic_import_detected", reason, candidate)
        if len(rejections) == 1 and self._approved_rejection(
            rejections[0], operation, candidate
        ):
            reason = "The only rejection is Radarr's exact not-an-upgrade condition"
            self.operations.transition(movie_id, "manual_import_ready", reason)
            return ManualImportReadiness("manual_import_ready", reason, candidate)
        return self._inspection_result(movie_id, "blocked", "Candidate contains an unapproved or additional rejection")

    @classmethod
    def _approved_rejection(cls, rejection, operation, candidate):
        if rejection == cls._APPROVED_REJECTION:
            return True

        match = cls._STRUCTURED_REJECTION.fullmatch(rejection)
        if match is None:
            return False
        try:
            original_name = operation.original_quality["quality"]["name"]
            candidate_name = candidate["quality"]["quality"]["name"]
        except (KeyError, TypeError):
            return False
        if not isinstance(original_name, str) or not original_name.strip():
            return False
        if not isinstance(candidate_name, str) or not candidate_name.strip():
            return False
        return (
            match.group("existing").strip().casefold()
            == original_name.strip().casefold()
            and match.group("new").strip().casefold()
            == candidate_name.strip().casefold()
        )

    def _inspection_result(self, movie_id, state, reason):
        self.operations.transition(movie_id, state, reason)
        return ManualImportReadiness(state, reason)

    @staticmethod
    def _candidate_safety_reason(candidate, operation):
        movie = candidate.get("movie")
        candidate_movie_id = movie.get("id") if isinstance(movie, dict) else None
        if (
            not isinstance(candidate_movie_id, int)
            or isinstance(candidate_movie_id, bool)
            or candidate_movie_id <= 0
            or candidate_movie_id != operation.movie_id
        ):
            return "Candidate movie ID does not exactly match the operation"
        candidate_download_id = candidate.get("downloadId")
        if candidate_download_id is not None and candidate_download_id != operation.download_id:
            return "Candidate download ID does not exactly match the operation"
        path = candidate.get("path")
        if not isinstance(path, str) or not path.strip() or not PurePosixPath(path).is_absolute():
            return "Candidate path is not a non-empty absolute POSIX path"
        original = PurePosixPath(operation.original_file_path)
        candidate_path = PurePosixPath(path)
        if candidate_path == original or (
            not original.is_absolute() and tuple(candidate_path.parts[-len(original.parts):]) == original.parts
        ):
            return "Candidate path is the original library file path"
        candidate_size = candidate.get("size")
        if not isinstance(candidate_size, int) or isinstance(candidate_size, bool) or candidate_size <= 0:
            return "Candidate size is not a positive integer"
        if candidate_size >= operation.original_file_size:
            return "Candidate is not smaller than the original file"
        if not isinstance(candidate.get("quality"), dict) or not candidate["quality"]:
            return "Candidate quality is missing"
        if not isinstance(candidate.get("languages"), list) or not candidate["languages"]:
            return "Candidate languages are missing"
        return None

    @classmethod
    def _normalized_rejections(cls, raw_rejections):
        if not isinstance(raw_rejections, list):
            return None
        normalized = []
        for rejection in raw_rejections:
            if isinstance(rejection, str):
                reason = rejection
            elif isinstance(rejection, dict) and set(rejection).issubset({"reason", "type"}):
                reason = rejection.get("reason")
            else:
                return None
            if not isinstance(reason, str) or not reason.strip():
                return None
            normalized.append(reason.strip().casefold())
        return normalized

    @staticmethod
    def _validate_movie_id(movie_id):
        if (
            not isinstance(movie_id, int)
            or isinstance(movie_id, bool)
            or movie_id <= 0
        ):
            raise ValueError("downgrade workflow requires a positive integer movie ID")

    @staticmethod
    def _matching_queue_item(movie_id, candidate, download_id, records):
        for item in records:
            if item.get("movieId") != movie_id:
                continue
            item_id = item.get("downloadId") or item.get("downloadClientId")
            if download_id and item_id and str(item_id) != str(download_id):
                continue
            if item.get("title") != candidate.release_name:
                continue
            protocol = item.get("protocol")
            if candidate.protocol and protocol and protocol.casefold() != candidate.protocol.casefold():
                continue
            return item
        return None

    @staticmethod
    def _downloading(item):
        status = str(item.get("status", "")).casefold()
        tracked = str(item.get("trackedDownloadStatus", "")).casefold()
        return status == "downloading" or tracked == "downloading"
