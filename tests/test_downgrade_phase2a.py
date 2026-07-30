import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from models.downgrade import DowngradeSuppression
from routes.webhook_routes import should_suppress_movie_notification
from services.downgrade_operation_service import (
    DowngradeOperationService, DuplicateDowngrade, RadarrRejected, ReleaseUnavailable,
)
from services.downgrade_service import DowngradeService
from services.downgrade_suppression_store import DowngradeSuppressionStore


def release(**extra):
    value = {"guid": "g-1", "indexerId": 4, "releaseTitle": "Film.1080p", "size": 40, "protocol": "usenet"}
    value.update(extra)
    return value


def candidate():
    return DowngradeService._normalize({**release(), "resolution": "1080p", "languages": ["English"]}, "Film", 100, 1080)


def http_error(status):
    return requests.HTTPError(response=Mock(status_code=status))


class DowngradePhase2ATests(unittest.TestCase):
    def store(self, directory):
        return DowngradeSuppressionStore(Path(directory) / "state.json")

    def configured_radarr(self, queue=None, grab=None):
        radarr = Mock()
        radarr.manual_search.return_value = [release()]
        radarr.grab_release.return_value = grab or {}
        radarr.get_queue.return_value = queue or []
        return radarr

    def test_refresh_matches_guid_indexer_title_and_size(self):
        selected = candidate(); radarr = Mock()
        radarr.manual_search.return_value = [release(size=41), release(indexerId=5), release()]
        exact = DowngradeService(radarr, Mock()).refresh_exact_movie_release(7, selected)
        self.assertIs(exact, radarr.manual_search.return_value[2])
        radarr.manual_search.assert_called_once_with(7)

    def test_stale_candidate_never_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            radarr = Mock(); radarr.manual_search.return_value = []
            with self.assertRaises(ReleaseUnavailable):
                DowngradeOperationService(radarr, self.store(directory), timeout=0).run(7, candidate())
            radarr.grab_release.assert_not_called()

    def test_exact_release_is_suppressed_before_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            events = []; store = self.store(directory); original_add = store.add
            store.add = Mock(side_effect=lambda value: (events.append("suppress"), original_add(value)))
            radarr = self.configured_radarr(
                [{"movieId": 7, "title": "Film.1080p", "downloadId": "d1", "protocol": "usenet", "status": "downloading", "downloadClient": "SABnzbd"}],
                {"downloadId": "d1"},
            )
            raw = radarr.manual_search.return_value[0]
            original_grab = radarr.grab_release
            original_grab.side_effect = lambda value: (events.append("post") or {"downloadId": "d1"})
            result = DowngradeOperationService(radarr, store, timeout=1, poll_interval=0).run(7, candidate())
            self.assertEqual(events, ["suppress", "post"])
            self.assertIs(radarr.grab_release.call_args.args[0], raw)
            self.assertEqual(result.downloader, "SABnzbd")

    def test_active_suppression_blocks_after_download_start_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            for queue, timeout in (([{"movieId": 7, "title": "Film.1080p", "protocol": "usenet", "status": "downloading"}], 1), ([], 0)):
                store = self.store(directory); radarr = self.configured_radarr(queue)
                DowngradeOperationService(radarr, store, timeout=timeout, poll_interval=0).run(7, candidate())
                with self.assertRaises(DuplicateDowngrade):
                    DowngradeOperationService(radarr, store, timeout=0).run(7, candidate())
                store.remove(7)

    def test_active_movie_lock_rejects_simultaneous_call(self):
        entered = threading.Event(); release_first = threading.Event()
        class Discovery:
            def refresh_exact_movie_release(self, movie_id, selected):
                entered.set(); release_first.wait(1); return None
        suppressions = Mock(); suppressions.has_active.return_value = False
        operation = DowngradeOperationService(Mock(), suppressions, Discovery())
        thread = threading.Thread(target=lambda: self.assertRaises(ReleaseUnavailable, operation.run, 7, candidate()))
        thread.start(); entered.wait(1)
        with self.assertRaises(DuplicateDowngrade): operation.run(7, candidate())
        release_first.set(); thread.join()

    def test_only_http_4xx_is_a_definitive_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            cases = ((http_error(400), RadarrRejected, False), (http_error(500), requests.HTTPError, True), (requests.HTTPError(), requests.HTTPError, True), (requests.ConnectionError(), requests.ConnectionError, True), (requests.Timeout(), requests.Timeout, True))
            for error, expected_error, remains in cases:
                store = self.store(directory); radarr = self.configured_radarr(); radarr.grab_release.side_effect = error
                with self.assertRaises(expected_error):
                    DowngradeOperationService(radarr, store).run(7, candidate())
                self.assertEqual(store.has_active(7), remains)
                store.remove(7)

    def test_queue_states_and_exact_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            queued = {"movieId": 7, "title": "Film.1080p", "protocol": "usenet", "status": "queued"}
            statuses = []
            result = DowngradeOperationService(self.configured_radarr([queued]), self.store(directory), timeout=.01, poll_interval=.02).run(7, candidate(), statuses.append)
            self.assertEqual(result.state, "timeout"); self.assertEqual(statuses[:2], ["waiting", "queued"])
            records = [{"movieId": 7, "title": "Film.1080p.EXTRA"}, {"movieId": 8, "title": "Film.1080p"}]
            self.assertIsNone(DowngradeOperationService._matching_queue_item(7, candidate(), None, records))

    def test_import_requires_download_event_and_more_than_movie_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory); store.add(DowngradeSuppression(7, "g-1", "Film.1080p", 4, "d1"))
            for payload in ({"movie": {"id": 7}, "downloadId": "d1"}, {"eventType": "Download", "movie": {"id": 7}}, {"eventType": "Download", "movie": {"id": 7}, "downloadId": "wrong"}):
                self.assertFalse(store.consume_matching_import(payload))
            self.assertTrue(store.has_active(7))

    def test_matching_download_id_consumes_exactly_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory); store.add(DowngradeSuppression(7, "g-1", "Film.1080p", 4, "d1"))
            payload = {"eventType": "Download", "movie": {"id": 7}, "downloadId": "d1"}
            self.assertTrue(should_suppress_movie_notification(payload, store))
            self.assertFalse(should_suppress_movie_notification(payload, store))
            self.assertFalse(store.has_active(7))

    def test_fallback_requires_exact_release_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory); store.add(DowngradeSuppression(7, "g-1", "Film.1080p", 4))
            self.assertFalse(store.consume_matching_import({"eventType": "Download", "movie": {"id": 7}}))
            self.assertFalse(store.consume_matching_import({"eventType": "Download", "movie": {"id": 7}, "releaseTitle": "Film.1080p.EXTRA"}))
            self.assertTrue(store.consume_matching_import({"eventType": "Download", "movie": {"id": 7}, "releaseTitle": "Film.1080p", "guid": "g-1", "indexerId": 4}))

    def test_persistence_restart_expiration_and_malformed_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; store = DowngradeSuppressionStore(path)
            store.add(DowngradeSuppression(7, "g", "name"))
            self.assertTrue(DowngradeSuppressionStore(path).has_active(7))
            data = json.loads(path.read_text())
            data["records"]["bad"] = {"movie_id": "bad", "created_at": "not-a-date"}
            path.write_text(json.dumps(data))
            self.assertTrue(DowngradeSuppressionStore(path).has_active(7))
            expired = DowngradeSuppression(8, "g", "name", created_at=(datetime.now(timezone.utc)-timedelta(hours=25)).isoformat())
            store.add(expired)
            self.assertFalse(store.has_active(8))

    def test_repeated_instances_use_unique_temporary_files_without_lost_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; first = DowngradeSuppressionStore(path); second = DowngradeSuppressionStore(path)
            names = []
            real_named_temporary = tempfile.NamedTemporaryFile
            def capture(*args, **kwargs):
                result = real_named_temporary(*args, **kwargs); names.append(result.name); return result
            with patch("services.downgrade_suppression_store.tempfile.NamedTemporaryFile", side_effect=capture):
                first.add(DowngradeSuppression(7, "g", "one"))
                second.add(DowngradeSuppression(8, "g", "two"))
            reloaded = DowngradeSuppressionStore(path)
            self.assertTrue(reloaded.has_active(7)); self.assertTrue(reloaded.has_active(8))
            self.assertEqual(len(names), len(set(names)))
