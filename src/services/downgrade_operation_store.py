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
