"""Persistent, narrowly scoped requester-notification suppressions."""
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.downgrade import DowngradeSuppression
from services.log_service import logger


class DowngradeSuppressionStore:
    VERSION = 1
    REPLACE_RETRIES = 3
    REPLACE_RETRY_DELAY_SECONDS = 0.05
    _process_lock = threading.RLock()

    def __init__(self, state_file=Path("data/downgrade_suppressions.json"), lifetime=timedelta(hours=24)):
        self.state_file, self.lifetime = Path(state_file), lifetime
        # One lock covers every instance so tests and transitional callers cannot
        # race an atomic replace using stale in-memory snapshots.
        self._lock = self._process_lock
        self._records = self._load()
        self._clean_expired()

    def _load(self):
        try:
            data = json.loads(self.state_file.read_text())
            if data.get("version") != self.VERSION or not isinstance(data.get("records", {}), dict):
                raise ValueError("unsupported or malformed state")
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            logger.warning("Failed to load downgrade suppression state: %s", error)
            return {}

        records = {}
        for key, value in data.get("records", {}).items():
            try:
                record = DowngradeSuppression.from_dict(value)
                movie_id = int(key)
                if record.movie_id != movie_id:
                    raise ValueError("movie ID does not match record key")
                datetime.fromisoformat(record.created_at)
                records[movie_id] = record
            except (KeyError, TypeError, ValueError) as error:
                logger.warning("Ignoring malformed downgrade suppression record %s: %s", key, error)
        return records

    def _save(self):
        data = {"version": self.VERSION, "records": {str(key): value.to_dict() for key, value in self._records.items()}}
        temporary_name = None
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.state_file.parent, prefix=f".{self.state_file.name}.", suffix=".tmp", delete=False) as temporary:
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

    def _clean_expired(self):
        with self._lock:
            now = datetime.now(timezone.utc)
            expired = []
            for key, record in self._records.items():
                try:
                    created = datetime.fromisoformat(record.created_at)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if now - created >= self.lifetime:
                        expired.append(key)
                except (TypeError, ValueError):
                    expired.append(key)
            if expired:
                previous = self._records.copy()
                for key in expired:
                    del self._records[key]
                try:
                    self._save()
                except OSError:
                    self._records = previous
                    raise

    def has_active(self, movie_id):
        with self._lock:
            self._records = self._load()
            self._clean_expired()
            return movie_id in self._records

    def add(self, record):
        with self._lock:
            self._records = self._load()
            self._clean_expired()
            previous = self._records.get(record.movie_id)
            self._records[record.movie_id] = record
            try:
                self._save()
            except OSError:
                if previous is None:
                    del self._records[record.movie_id]
                else:
                    self._records[record.movie_id] = previous
                raise

    def remove(self, movie_id):
        with self._lock:
            self._records = self._load()
            record = self._records.pop(movie_id, None)
            if record is not None:
                try:
                    self._save()
                except OSError:
                    self._records[movie_id] = record
                    raise

    def update_download_id(self, movie_id, download_id):
        if not download_id:
            return
        with self._lock:
            self._records = self._load()
            record = self._records.get(movie_id)
            if record:
                previous = record.download_id
                record.download_id = str(download_id)
                try:
                    self._save()
                except OSError:
                    record.download_id = previous
                    raise

    def consume_matching_import(self, payload):
        """Atomically consume one exact Download webhook suppression."""
        if str(payload.get("eventType", "")).casefold() != "download":
            return False
        movie_id = payload.get("movie", {}).get("id")
        if not isinstance(movie_id, int) or isinstance(movie_id, bool):
            return False
        with self._lock:
            self._records = self._load()
            self._clean_expired()
            record = self._records.get(movie_id)
            if record is None:
                return False
            identity = payload.get("release") if isinstance(payload.get("release"), dict) else payload
            guid = identity.get("guid")
            indexer_id = identity.get("indexerId")
            if guid is not None and str(guid) != record.guid:
                return False
            if indexer_id is not None and indexer_id != record.indexer_id:
                return False
            webhook_download_id = payload.get("downloadId") or payload.get("downloadClientId")
            if record.download_id:
                if webhook_download_id is None or str(webhook_download_id) != record.download_id:
                    return False
                basis = "download ID"
            else:
                release_name = identity.get("releaseTitle") or identity.get("releaseName")
                if not release_name or release_name != record.release_name:
                    return False
                basis = "exact release identity"
            del self._records[movie_id]
            try:
                self._save()
            except OSError:
                self._records[movie_id] = record
                raise
            logger.info("Consumed downgrade suppression for Radarr movie %s using %s", movie_id, basis)
            return True
