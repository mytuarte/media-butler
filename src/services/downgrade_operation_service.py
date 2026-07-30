"""Radarr replacement submission and bounded queue verification."""
import threading
import time
from dataclasses import dataclass

import requests

from models.downgrade import DowngradeSuppression, ReplacementCandidate
from services.downgrade_service import DowngradeService
from services.downgrade_suppression_store import DowngradeSuppressionStore


class ReleaseUnavailable(Exception):
    pass


class DuplicateDowngrade(Exception):
    pass


class RadarrRejected(Exception):
    pass


@dataclass
class DowngradeOutcome:
    state: str
    downloader: str | None = None


class DowngradeOperationService:
    _active = set()
    _active_lock = threading.Lock()

    def __init__(self, radarr, suppression_store=None, discovery=None, timeout=75, poll_interval=3):
        self.radarr = radarr
        self.suppressions = suppression_store or DowngradeSuppressionStore()
        self.discovery = discovery or DowngradeService(radarr=radarr)
        self.timeout, self.poll_interval = timeout, poll_interval

    def run(self, movie_id: int, candidate: ReplacementCandidate, status=lambda value: None):
        with self._active_lock:
            if movie_id in self._active or self.suppressions.has_active(movie_id):
                raise DuplicateDowngrade()
            self._active.add(movie_id)
        try:
            raw_release = self.discovery.refresh_exact_movie_release(movie_id, candidate)
            if raw_release is None:
                raise ReleaseUnavailable()
            record = DowngradeSuppression(movie_id, candidate.guid or "", candidate.release_name or "", candidate.indexer_id)
            self.suppressions.add(record)  # Must be durable before the POST.
            try:
                response = self.radarr.grab_release(raw_release)
            except requests.HTTPError as error:
                status_code = getattr(error.response, "status_code", None)
                if isinstance(status_code, int) and 400 <= status_code < 500:
                    self.suppressions.remove(movie_id)
                    raise RadarrRejected() from error
                raise
            download_id = response.get("downloadId") or response.get("downloadClientId")
            self.suppressions.update_download_id(movie_id, download_id)
            status("waiting")
            deadline = time.monotonic() + self.timeout
            queued_reported = False
            while time.monotonic() < deadline:
                item = self._matching_queue_item(movie_id, candidate, download_id, self.radarr.get_queue())
                if item:
                    found_id = item.get("downloadId") or item.get("downloadClientId")
                    self.suppressions.update_download_id(movie_id, found_id)
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
