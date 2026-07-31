"""Restart-safe persistent state for active movie downgrade operations."""
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from models.downgrade import DOWNGRADE_OPERATION_STATES, DowngradeOperation


class DowngradeOperationStoreError(RuntimeError):
    """Raised when persisted downgrade state cannot be trusted safely."""


class DuplicateDowngradeOperationError(DowngradeOperationStoreError):
    """Raised when creation would overwrite an existing movie operation."""


class MissingDowngradeOperationError(DowngradeOperationStoreError):
    """Raised when a persistence operation targets a missing operation."""


class ManualImportSubmissionClaimError(DowngradeOperationStoreError):
    """Raised when an operation cannot be claimed for one manual-import POST."""


class DowngradeOperationStore:
    VERSION = 1
    REPLACE_RETRIES = 3
    REPLACE_RETRY_DELAY_SECONDS = 0.05
    _process_lock = threading.RLock()

    def __init__(self, state_file=Path("data/downgrade_operations.json")):
        self.state_file = Path(state_file)
        self._lock = self._process_lock
        self._records = self._load()

    def _load(self):
        try:
            data = json.loads(self.state_file.read_text())
            if not isinstance(data, dict) or data.get("version") != self.VERSION:
                raise ValueError("unsupported operation state")
            raw_records = data.get("records")
            if not isinstance(raw_records, dict):
                raise ValueError("operation records must be an object")
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise DowngradeOperationStoreError(
                f"Downgrade operation state cannot be loaded safely: {error}"
            ) from error

        records = {}
        for key, value in raw_records.items():
            try:
                movie_id = int(key)
                record = DowngradeOperation.from_dict(value)
                if str(movie_id) != key or record.movie_id != movie_id:
                    raise ValueError("movie ID does not match record key")
                records[movie_id] = record
            except (KeyError, TypeError, ValueError) as error:
                raise DowngradeOperationStoreError(
                    f"Downgrade operation record {key!r} is malformed: {error}"
                ) from error
        return records

    def _save(self):
        data = {"version": self.VERSION, "records": {
            str(key): value.to_dict() for key, value in self._records.items()
        }}
        temporary_name = None
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.state_file.parent,
                prefix=f".{self.state_file.name}.", suffix=".tmp", delete=False,
            ) as temporary:
                temporary_name = temporary.name
                json.dump(data, temporary, indent=2, sort_keys=True)
                temporary.flush()
                os.fsync(temporary.fileno())
            for attempt in range(self.REPLACE_RETRIES):
                try:
                    os.replace(temporary_name, self.state_file)
                    temporary_name = None
                    return
                except OSError:
                    if attempt == self.REPLACE_RETRIES - 1:
                        raise
                    time.sleep(self.REPLACE_RETRY_DELAY_SECONDS * (attempt + 1))
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

    def get(self, movie_id):
        self._validate_movie_id(movie_id)
        with self._lock:
            self._records = self._load()
            return self._records.get(movie_id)

    def save(self, record):
        DowngradeOperation.from_dict(record.to_dict())
        with self._lock:
            self._records = self._load()
            if record.movie_id in self._records:
                raise DuplicateDowngradeOperationError(
                    f"Downgrade operation already exists for movie {record.movie_id}"
                )
            self._records[record.movie_id] = record
            try:
                self._save()
            except OSError:
                self._records.pop(record.movie_id, None)
                raise

    def update(self, movie_id, **changes):
        self._validate_movie_id(movie_id)
        mutable_fields = {"state", "download_id", "last_safe_diagnostic_reason"}
        unsupported = set(changes) - mutable_fields
        if unsupported:
            raise ValueError(
                f"unsupported operation update: {sorted(unsupported)[0]}"
            )
        with self._lock:
            self._records = self._load()
            record = self._records.get(movie_id)
            if record is None:
                return None
            previous = record.to_dict()
            for key, value in changes.items():
                if (
                    key == "state"
                    and record.state in {
                        "submitting_manual_import", "manual_import_submitted",
                        "verifying_replacement", "replacement_verified",
                        "manual_import_failed", "ambiguous",
                    }
                    and value in {"inspecting_import", "manual_import_ready"}
                ):
                    raise DowngradeOperationStoreError(
                        f"Cannot reopen manual import from {record.state}"
                    )
                if (
                    key == "download_id"
                    and record.replacement_candidate_path is not None
                    and record.download_id != value
                ):
                    raise ValueError(
                        "download_id is immutable after candidate persistence"
                    )
                setattr(record, key, value)
            record.updated_at = datetime.now(timezone.utc).isoformat()
            try:
                DowngradeOperation.from_dict(record.to_dict())
                self._save()
            except (OSError, ValueError, TypeError):
                self._records[movie_id] = DowngradeOperation.from_dict(previous)
                raise
            return record

    def transition(self, movie_id, state, reason):
        self._validate_movie_id(movie_id)
        if state not in DOWNGRADE_OPERATION_STATES:
            raise ValueError("unsupported operation state")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a safe diagnostic reason is required")
        return self.update(movie_id, state=state, last_safe_diagnostic_reason=reason)

    def transition_if_current(
        self, movie_id, allowed_current_states, new_state, reason,
    ):
        """Atomically transition only a current non-terminal lifecycle state."""
        self._validate_movie_id(movie_id)
        if not isinstance(allowed_current_states, (set, frozenset, tuple, list)):
            raise ValueError("allowed current states must be a collection")
        allowed = frozenset(allowed_current_states)
        if not allowed or not allowed.issubset(DOWNGRADE_OPERATION_STATES):
            raise ValueError("allowed current states are invalid")
        if new_state not in DOWNGRADE_OPERATION_STATES:
            raise ValueError("unsupported operation state")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a safe diagnostic reason is required")
        with self._lock:
            self._records = self._load()
            record = self._records.get(movie_id)
            if record is None:
                raise MissingDowngradeOperationError(
                    f"Downgrade operation does not exist for movie {movie_id}"
                )
            if record.state in {"replacement_verified", "manual_import_failed"}:
                return record
            if record.state not in allowed:
                return record
            previous = record.to_dict()
            record.state = new_state
            record.last_safe_diagnostic_reason = reason
            record.updated_at = datetime.now(timezone.utc).isoformat()
            try:
                DowngradeOperation.from_dict(record.to_dict())
                self._save()
            except (OSError, ValueError, TypeError):
                self._records[movie_id] = DowngradeOperation.from_dict(previous)
                raise
            return record

    def set_replacement_candidate(self, movie_id, path, size, quality):
        """Persist candidate identity once, without making identity generally mutable."""
        return self._set_once(movie_id, {
            "replacement_candidate_path": path,
            "replacement_candidate_size": size,
            "replacement_candidate_quality": quality,
        })

    def claim_manual_import_submission(
        self, movie_id, candidate_path, candidate_size, candidate_quality,
        diagnostic_reason,
    ):
        """Atomically claim the sole right to issue a manual-import POST."""
        self._validate_movie_id(movie_id)
        if not isinstance(diagnostic_reason, str) or not diagnostic_reason.strip():
            raise ValueError("a safe diagnostic reason is required")
        with self._lock:
            self._records = self._load()
            record = self._records.get(movie_id)
            if record is None:
                raise MissingDowngradeOperationError(
                    f"Downgrade operation does not exist for movie {movie_id}"
                )
            if record.state != "manual_import_ready":
                raise ManualImportSubmissionClaimError(
                    f"Manual import is already claimed in state {record.state}"
                )
            if record.manual_import_command_id is not None:
                raise ManualImportSubmissionClaimError(
                    "Manual-import command ID is already persisted"
                )
            if not isinstance(record.download_id, str) or not record.download_id.strip():
                raise ManualImportSubmissionClaimError(
                    "Exact download ID is unavailable"
                )
            supplied = (candidate_path, candidate_size, candidate_quality)
            existing = (
                record.replacement_candidate_path,
                record.replacement_candidate_size,
                record.replacement_candidate_quality,
            )
            if any(value is not None for value in existing) and existing != supplied:
                raise ManualImportSubmissionClaimError(
                    "Persisted replacement candidate identity differs"
                )
            previous = record.to_dict()
            record.replacement_candidate_path = candidate_path
            record.replacement_candidate_size = candidate_size
            record.replacement_candidate_quality = candidate_quality
            record.state = "submitting_manual_import"
            record.last_safe_diagnostic_reason = diagnostic_reason
            record.updated_at = datetime.now(timezone.utc).isoformat()
            try:
                DowngradeOperation.from_dict(record.to_dict())
                self._save()
            except (OSError, ValueError, TypeError):
                self._records[movie_id] = DowngradeOperation.from_dict(previous)
                raise
            return record

    def begin_replacement_verification(self, movie_id, reason):
        """Atomically enter verification without reopening a terminal record."""
        self._validate_movie_id(movie_id)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a safe diagnostic reason is required")
        with self._lock:
            self._records = self._load()
            record = self._records.get(movie_id)
            if record is None:
                raise MissingDowngradeOperationError(
                    f"Downgrade operation does not exist for movie {movie_id}"
                )
            if record.state in {"verifying_replacement", "replacement_verified"}:
                return record
            if record.state != "manual_import_submitted":
                raise DowngradeOperationStoreError(
                    f"Operation cannot enter verification from {record.state}"
                )
            previous = record.to_dict()
            record.state = "verifying_replacement"
            record.last_safe_diagnostic_reason = reason
            record.updated_at = datetime.now(timezone.utc).isoformat()
            try:
                DowngradeOperation.from_dict(record.to_dict())
                self._save()
            except (OSError, ValueError, TypeError):
                self._records[movie_id] = DowngradeOperation.from_dict(previous)
                raise
            return record

    def set_manual_import_command(self, movie_id, command_id, submitted_at):
        """Persist the submitted command identity once."""
        return self._set_once(movie_id, {
            "manual_import_command_id": command_id,
            "manual_import_submitted_at": submitted_at,
        })

    def save_verified_replacement(self, movie_id, snapshot, verified_at, reason):
        """Atomically persist the complete terminal replacement identity."""
        self._validate_movie_id(movie_id)
        if not isinstance(snapshot, dict):
            raise ValueError("verified replacement snapshot must be an object")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a safe diagnostic reason is required")
        with self._lock:
            self._records = self._load()
            record = self._records.get(movie_id)
            if record is None:
                raise MissingDowngradeOperationError(
                    f"Downgrade operation does not exist for movie {movie_id}"
                )
            snapshot_movie_id = snapshot.get("movie_id")
            if (
                not isinstance(snapshot_movie_id, int)
                or isinstance(snapshot_movie_id, bool)
                or snapshot_movie_id <= 0
                or snapshot_movie_id != record.movie_id
            ):
                raise ValueError("verified replacement movie ID does not match")
            if record.state == "replacement_verified":
                expected = (
                    record.final_replacement_movie_file_id,
                    record.final_replacement_path,
                    record.final_replacement_size,
                    record.final_replacement_quality,
                )
                supplied = (
                    snapshot.get("movie_file_id"), snapshot.get("path"),
                    snapshot.get("size"), snapshot.get("quality"),
                )
                if expected != supplied:
                    raise ValueError("verified replacement identity is immutable")
                return record
            previous = record.to_dict()
            record.state = "replacement_verified"
            record.replacement_verified_at = verified_at
            record.final_replacement_movie_file_id = snapshot.get("movie_file_id")
            record.final_replacement_path = snapshot.get("path")
            record.final_replacement_size = snapshot.get("size")
            record.final_replacement_quality = snapshot.get("quality")
            record.last_safe_diagnostic_reason = reason
            record.updated_at = datetime.now(timezone.utc).isoformat()
            try:
                DowngradeOperation.from_dict(record.to_dict())
                self._save()
            except (OSError, ValueError, TypeError):
                self._records[movie_id] = DowngradeOperation.from_dict(previous)
                raise
            return record

    def _set_once(self, movie_id, changes):
        self._validate_movie_id(movie_id)
        with self._lock:
            self._records = self._load()
            record = self._records.get(movie_id)
            if record is None:
                raise MissingDowngradeOperationError(
                    f"Downgrade operation does not exist for movie {movie_id}"
                )
            previous = record.to_dict()
            for key, value in changes.items():
                current = getattr(record, key)
                if current is not None and current != value:
                    raise ValueError(f"{key} is immutable once persisted")
                setattr(record, key, value)
            record.updated_at = datetime.now(timezone.utc).isoformat()
            try:
                DowngradeOperation.from_dict(record.to_dict())
                self._save()
            except (OSError, ValueError, TypeError):
                self._records[movie_id] = DowngradeOperation.from_dict(previous)
                raise
            return record

    def remove(self, movie_id):
        self._validate_movie_id(movie_id)
        with self._lock:
            self._records = self._load()
            previous = self._records.pop(movie_id, None)
            if previous is not None:
                try:
                    self._save()
                except OSError:
                    self._records[movie_id] = previous
                    raise

    @staticmethod
    def _validate_movie_id(movie_id):
        if (
            not isinstance(movie_id, int)
            or isinstance(movie_id, bool)
            or movie_id <= 0
        ):
            raise ValueError("downgrade operation requires a positive integer movie ID")
