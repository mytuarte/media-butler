"""Radarr replacement submission and read-only import-readiness inspection."""
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import requests

from models.downgrade import DowngradeOperation, DowngradeSuppression, ReplacementCandidate
from services.downgrade_operation_store import (
    DowngradeOperationStore,
    DowngradeOperationStoreError,
    ManualImportSubmissionClaimError,
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


@dataclass(frozen=True)
class ManualImportExecutionResult:
    state: str
    reason: str
    command_id: int | None = None


@dataclass(frozen=True)
class ReplacementVerificationResult:
    state: str
    reason: str
    original_snapshot: dict | None = None
    replacement_snapshot: dict | None = None
    replacement_verified_at: str | None = None


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

    def execute_ready_manual_import(self, movie_id: int) -> ManualImportExecutionResult:
        """Freshly validate and submit exactly one restart-safe manual import."""
        self._validate_movie_id(movie_id)
        operation = self.operations.get(movie_id)
        if operation is None:
            return ManualImportExecutionResult("blocked", "No persisted downgrade operation exists")
        if operation.state != "manual_import_ready":
            return ManualImportExecutionResult(
                operation.state, "Only a manual_import_ready operation may be submitted",
                operation.manual_import_command_id,
            )
        if not isinstance(operation.download_id, str) or not operation.download_id.strip():
            return self._execution_transition(movie_id, "ambiguous", "The exact download ID is unavailable")
        if operation.manual_import_command_id is not None:
            return ManualImportExecutionResult(
                "manual_import_submitted", "A manual-import command is already persisted",
                operation.manual_import_command_id,
            )

        readiness = self._fresh_manual_import_readiness(operation)
        if readiness.state != "manual_import_ready" or readiness.candidate is None:
            try:
                persisted_readiness = self.operations.transition(
                    movie_id, readiness.state, readiness.reason,
                )
                if persisted_readiness is not None:
                    return ManualImportExecutionResult(
                        persisted_readiness.state,
                        persisted_readiness.last_safe_diagnostic_reason,
                        persisted_readiness.manual_import_command_id,
                    )
            except Exception:
                try:
                    persisted_readiness = self.operations.get(movie_id)
                except Exception:
                    persisted_readiness = None
                if persisted_readiness is not None:
                    return ManualImportExecutionResult(
                        persisted_readiness.state,
                        persisted_readiness.last_safe_diagnostic_reason,
                        persisted_readiness.manual_import_command_id,
                    )
            return ManualImportExecutionResult("ambiguous", readiness.reason)
        candidate = readiness.candidate
        identity = (candidate.get("path"), candidate.get("size"), candidate.get("quality"))
        persisted_identity = (
            operation.replacement_candidate_path,
            operation.replacement_candidate_size,
            operation.replacement_candidate_quality,
        )
        if any(value is not None for value in persisted_identity) and identity != persisted_identity:
            return self._execution_transition(
                movie_id, "blocked", "Fresh manual-import candidate identity changed",
            )

        try:
            current = self.radarr.get_movie_file_snapshot(movie_id)
        except Exception:
            return self._execution_transition(movie_id, "ambiguous", "Current movie-file snapshot could not be trusted")
        mismatch = self._original_snapshot_mismatch(operation, current)
        if mismatch:
            return self._execution_transition(movie_id, "blocked", mismatch)

        try:
            suppression = self.suppressions.get(movie_id)
        except Exception:
            suppression = None
        if (
            suppression is None
            or suppression.movie_id != movie_id
            or not isinstance(suppression.download_id, str)
            or suppression.download_id != operation.download_id
        ):
            return self._execution_transition(
                movie_id, "blocked", "Exact durable downgrade suppression is unavailable or mismatched",
            )

        claim_reason = "Exact candidate persisted; submitting one Radarr manual-import command"
        try:
            persisted_candidate = self.operations.claim_manual_import_submission(
                movie_id, *identity, claim_reason,
            )
            if (
                persisted_candidate is None
                or (
                    persisted_candidate.replacement_candidate_path,
                    persisted_candidate.replacement_candidate_size,
                    persisted_candidate.replacement_candidate_quality,
                ) != identity
            ):
                raise ValueError("candidate persistence was not confirmed")
            if persisted_candidate.state != "submitting_manual_import":
                raise ValueError("submitting state persistence was not confirmed")
        except ManualImportSubmissionClaimError:
            try:
                claimed = self.operations.get(movie_id)
            except Exception:
                claimed = None
            if claimed is None:
                return ManualImportExecutionResult(
                    "ambiguous", "Manual-import submission claim is ambiguous",
                )
            return ManualImportExecutionResult(
                claimed.state, claimed.last_safe_diagnostic_reason,
                claimed.manual_import_command_id,
            )
        except Exception:
            return self._execution_transition(
                movie_id, "ambiguous", "Candidate persistence could not be confirmed before submission",
            )

        try:
            response = self.radarr.submit_manual_import_candidate(
                candidate, operation.download_id, movie_id,
            )
        except requests.HTTPError as error:
            status_code = getattr(error.response, "status_code", None)
            if isinstance(status_code, int) and 400 <= status_code < 500:
                return self._execution_transition(
                    movie_id, "manual_import_failed", "Radarr definitively rejected the manual import",
                )
            return self._execution_transition(movie_id, "ambiguous", "Manual-import submission outcome is ambiguous")
        except Exception:
            return self._execution_transition(movie_id, "ambiguous", "Manual-import submission outcome is ambiguous")

        command_id = response.get("id") if isinstance(response, dict) else None
        if not isinstance(command_id, int) or isinstance(command_id, bool) or command_id <= 0:
            return self._execution_transition(movie_id, "ambiguous", "Radarr returned a malformed command response")
        submitted_at = datetime.now(timezone.utc).isoformat()
        try:
            persisted_command = self.operations.set_manual_import_command(
                movie_id, command_id, submitted_at,
            )
            if (
                persisted_command is None
                or persisted_command.manual_import_command_id != command_id
                or persisted_command.manual_import_submitted_at != submitted_at
            ):
                raise ValueError("command persistence was not confirmed")
            submitted = self.operations.transition(
                movie_id, "manual_import_submitted", "Manual-import command submitted; awaiting status",
            )
            if (
                submitted is None
                or submitted.state != "manual_import_submitted"
                or submitted.manual_import_command_id != command_id
                or submitted.manual_import_submitted_at != submitted_at
            ):
                raise ValueError("submitted state persistence was not confirmed")
        except Exception:
            # The POST may have succeeded. Never convert this into a retryable state.
            return self._execution_transition(movie_id, "ambiguous", "Manual-import command persistence is ambiguous")
        return ManualImportExecutionResult(
            "manual_import_submitted", "Manual-import command submitted; awaiting status", command_id,
        )

    def _fresh_manual_import_readiness(self, operation):
        """Inspect execution readiness without reopening persistent lifecycle state."""
        try:
            candidates = self.radarr.get_manual_import_candidates(
                operation.download_id, operation.movie_id,
            )
        except Exception:
            return ManualImportReadiness(
                "ambiguous", "Radarr candidate inspection failed safely",
            )
        if not candidates:
            return ManualImportReadiness(
                "inspecting_import", "No manual-import candidates are available yet",
            )
        if len(candidates) != 1:
            return ManualImportReadiness(
                "blocked", "Multiple candidates cannot be selected without guessing",
            )
        candidate = candidates[0]
        unsafe_reason = self._candidate_safety_reason(candidate, operation)
        if unsafe_reason:
            return ManualImportReadiness("blocked", unsafe_reason)
        if "rejections" not in candidate:
            return ManualImportReadiness(
                "blocked", "Candidate rejection data is missing or malformed",
            )
        rejections = self._normalized_rejections(candidate.get("rejections"))
        if rejections is None:
            return ManualImportReadiness(
                "blocked", "Candidate rejection data is missing or malformed",
            )
        if not rejections:
            return ManualImportReadiness(
                "automatic_import_detected",
                "Safe candidate has no rejection; Radarr may be importing automatically",
                candidate,
            )
        if len(rejections) == 1 and self._approved_rejection(
            rejections[0], operation, candidate,
        ):
            return ManualImportReadiness(
                "manual_import_ready",
                "The only rejection is Radarr's exact not-an-upgrade condition",
                candidate,
            )
        return ManualImportReadiness(
            "blocked", "Candidate contains an unapproved or additional rejection",
        )

    def poll_manual_import_command(self, movie_id: int):
        """Poll one persisted command and verify completion without another POST."""
        self._validate_movie_id(movie_id)
        operation = self.operations.get(movie_id)
        if operation is None:
            return ManualImportExecutionResult("blocked", "No persisted downgrade operation exists")
        if operation.state == "replacement_verified":
            return self._persisted_verification_result(operation)
        if operation.state == "manual_import_failed":
            return ManualImportExecutionResult(
                "manual_import_failed", operation.last_safe_diagnostic_reason,
                operation.manual_import_command_id,
            )
        command_id = operation.manual_import_command_id
        if not isinstance(command_id, int) or isinstance(command_id, bool) or command_id <= 0:
            return self._execution_transition(movie_id, "ambiguous", "No exact manual-import command ID is persisted")
        try:
            command = self.radarr.get_command_status(command_id)
            if (
                not isinstance(command, dict)
                or command.get("id") != command_id
                or isinstance(command.get("id"), bool)
            ):
                raise ValueError("command response identity does not match")
            status = command.get("status")
        except Exception:
            return self._poll_transition(
                movie_id, {"manual_import_submitted"}, "ambiguous",
                "Manual-import command status is unavailable", command_id,
            )
        normalized = status.strip().casefold() if isinstance(status, str) else ""
        if normalized in {"queued", "started", "running"}:
            return self._poll_transition(
                movie_id, {"manual_import_submitted"},
                "manual_import_submitted", "Manual-import command is still running",
                command_id,
            )
        if normalized == "failed":
            return self._poll_transition(
                movie_id, {"manual_import_submitted"}, "manual_import_failed",
                "Radarr reports that manual import failed", command_id,
            )
        if normalized != "completed":
            return self._poll_transition(
                movie_id, {"manual_import_submitted"}, "ambiguous",
                "Manual-import command returned an unknown status", command_id,
            )
        try:
            verifying = self.operations.transition_if_current(
                movie_id, {"manual_import_submitted"}, "verifying_replacement",
                "Command completed; verifying Radarr's current movie file",
            )
        except Exception:
            return ManualImportExecutionResult(
                "ambiguous", "Replacement verification transition is ambiguous",
                command_id,
            )
        if verifying.state == "replacement_verified":
            return self._persisted_verification_result(verifying)
        if verifying.state == "manual_import_failed":
            return self._persisted_failure_result(verifying)
        if verifying.state != "verifying_replacement":
            return ManualImportExecutionResult(
                "ambiguous", "Replacement verification transition was not confirmed",
                command_id,
            )
        return self._verify_replacement(movie_id)

    def _verify_replacement(self, movie_id):
        operation = self.operations.get(movie_id)
        if operation is None:
            return ReplacementVerificationResult(
                "ambiguous", "Downgrade operation disappeared before verification",
            )
        try:
            suppression = self.suppressions.get(movie_id)
        except Exception:
            suppression = None
        if (
            suppression is None
            or suppression.movie_id != operation.movie_id
            or suppression.download_id != operation.download_id
        ):
            return self._verification_failure(
                movie_id, "Exact downgrade suppression identity changed before verification",
            )
        try:
            current = self.radarr.get_movie_file_snapshot(movie_id)
        except Exception:
            return self._verification_failure(movie_id, "Replacement snapshot is unavailable or malformed")
        reason = self._replacement_mismatch(operation, current)
        if reason:
            return self._verification_failure(movie_id, reason)
        verified_at = datetime.now(timezone.utc).isoformat()
        reason = "Exact smaller Radarr replacement verified"
        try:
            verified = self.operations.save_verified_replacement(
                movie_id, current, verified_at, reason,
            )
            if (
                verified is None
                or verified.state != "replacement_verified"
                or verified.replacement_verified_at is None
                or verified.final_replacement_movie_file_id != current.get("movie_file_id")
                or verified.final_replacement_path != current.get("path")
                or verified.final_replacement_size != current.get("size")
                or verified.final_replacement_quality != current.get("quality")
            ):
                raise ValueError("verified replacement persistence was not confirmed")
        except Exception:
            # The single atomic replace either committed the complete terminal
            # record or left the durable verifying state intact.
            return self._verification_failure(
                movie_id, "Replacement verification persistence is ambiguous",
            )
        original = {
            "movie_id": operation.movie_id, "movie_file_id": operation.original_movie_file_id,
            "path": operation.original_file_path, "size": operation.original_file_size,
            "quality": operation.original_quality,
        }
        replacement = {
            "movie_id": verified.movie_id,
            "movie_file_id": verified.final_replacement_movie_file_id,
            "path": verified.final_replacement_path,
            "size": verified.final_replacement_size,
            "quality": verified.final_replacement_quality,
        }
        return ReplacementVerificationResult(
            "replacement_verified", verified.last_safe_diagnostic_reason,
            original, replacement, verified.replacement_verified_at,
        )

    @staticmethod
    def _persisted_verification_result(operation):
        original = {
            "movie_id": operation.movie_id,
            "movie_file_id": operation.original_movie_file_id,
            "path": operation.original_file_path,
            "size": operation.original_file_size,
            "quality": operation.original_quality,
        }
        replacement = {
            "movie_id": operation.movie_id,
            "movie_file_id": operation.final_replacement_movie_file_id,
            "path": operation.final_replacement_path,
            "size": operation.final_replacement_size,
            "quality": operation.final_replacement_quality,
        }
        return ReplacementVerificationResult(
            "replacement_verified", operation.last_safe_diagnostic_reason,
            original, replacement, operation.replacement_verified_at,
        )

    def _verification_failure(self, movie_id, reason):
        try:
            record = self.operations.transition_if_current(
                movie_id, {"verifying_replacement"}, "ambiguous", reason,
            )
        except Exception:
            try:
                record = self.operations.get(movie_id)
            except Exception:
                record = None
        if record is not None and record.state == "replacement_verified":
            return self._persisted_verification_result(record)
        if record is not None and record.state == "manual_import_failed":
            return self._persisted_failure_result(record)
        return ReplacementVerificationResult("ambiguous", reason)

    def _poll_transition(self, movie_id, allowed, state, reason, command_id):
        try:
            record = self.operations.transition_if_current(
                movie_id, allowed, state, reason,
            )
        except Exception:
            try:
                record = self.operations.get(movie_id)
            except Exception:
                record = None
        if record is not None and record.state == "replacement_verified":
            return self._persisted_verification_result(record)
        if record is not None and record.state == "manual_import_failed":
            return self._persisted_failure_result(record)
        if record is not None:
            return ManualImportExecutionResult(
                record.state, record.last_safe_diagnostic_reason,
                record.manual_import_command_id,
            )
        return ManualImportExecutionResult("ambiguous", reason, command_id)

    @staticmethod
    def _persisted_failure_result(operation):
        return ManualImportExecutionResult(
            "manual_import_failed", operation.last_safe_diagnostic_reason,
            operation.manual_import_command_id,
        )

    def _execution_transition(self, movie_id, state, reason, command_id=None):
        try:
            self.operations.transition(movie_id, state, reason)
        except Exception:
            state, reason = "ambiguous", f"{reason}; state persistence is ambiguous"
        return ManualImportExecutionResult(state, reason, command_id)

    @classmethod
    def _original_snapshot_mismatch(cls, operation, current):
        if not isinstance(current, dict):
            return "Current movie file no longer exactly matches the persisted original"
        current_movie_id = current.get("movie_id")
        current_file_id = current.get("movie_file_id")
        if (
            not cls._is_positive_integer(current_movie_id)
            or not cls._is_positive_integer(current_file_id)
        ):
            return "Current movie file identity is malformed"
        expected = (
            operation.movie_id, operation.original_movie_file_id,
            operation.original_file_path, operation.original_file_size,
        )
        actual = (current_movie_id, current_file_id, current.get("path"), current.get("size"))
        if actual != expected:
            return "Current movie file no longer exactly matches the persisted original"
        original_quality = cls._quality_name(operation.original_quality)
        if original_quality is not None and cls._quality_name(current.get("quality")) != original_quality:
            return "Current movie-file quality no longer matches the persisted original"
        return None

    @classmethod
    def _replacement_mismatch(cls, operation, current):
        if not isinstance(current, dict):
            return "Replacement movie ID does not exactly match"
        current_movie_id = current.get("movie_id")
        if (
            not cls._is_positive_integer(current_movie_id)
            or current_movie_id != operation.movie_id
        ):
            return "Replacement movie ID does not exactly match"
        file_id = current.get("movie_file_id")
        size = current.get("size")
        if not isinstance(file_id, int) or isinstance(file_id, bool) or file_id <= 0 or file_id == operation.original_movie_file_id:
            return "Replacement movieFileId was not safely changed"
        if not isinstance(current.get("path"), str) or current["path"] == operation.original_file_path:
            return "Original movie-file path is still active"
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0 or size != operation.replacement_candidate_size:
            return "Replacement size does not match the persisted candidate"
        if size >= operation.original_file_size:
            return "Replacement is not smaller than the original"
        expected_quality = cls._quality_name(operation.replacement_candidate_quality)
        if expected_quality is None or cls._quality_name(current.get("quality")) != expected_quality:
            return "Replacement quality does not match the persisted candidate"
        return None

    @staticmethod
    def _is_positive_integer(value):
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @staticmethod
    def _quality_name(quality):
        if not isinstance(quality, dict):
            return None
        nested = quality.get("quality")
        name = nested.get("name") if isinstance(nested, dict) else quality.get("name")
        return name.strip().casefold() if isinstance(name, str) and name.strip() else None

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
