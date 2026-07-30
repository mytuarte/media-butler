import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from models.downgrade import DowngradeOperation
from services.downgrade_operation_service import (
    DowngradeOperationService,
    RadarrRejected,
    UnsafeOriginalMovieFile,
)
from services.downgrade_operation_store import (
    DuplicateDowngradeOperationError,
    DowngradeOperationStore,
    DowngradeOperationStoreError,
)
from services.downgrade_service import DowngradeService
from services.downgrade_suppression_store import DowngradeSuppressionStore


def selected():
    return DowngradeService._normalize({
        "guid": "guid", "indexerId": 4, "releaseTitle": "Film.1080p",
        "size": 40, "protocol": "usenet", "resolution": "1080p",
        "languages": ["English"],
    }, "Film", 100, 1080)


def operation(**changes):
    values = dict(
        movie_id=7, selected_release_name="Film.1080p", selected_release_guid="guid",
        selected_indexer_id=4, selected_release_size=40, selected_protocol="usenet",
        download_id="download-1", original_movie_file_id=70,
        original_file_path="/movies/Film.mkv", original_file_size=100,
        original_quality={"quality": {"name": "Bluray-2160p"}},
        state="waiting_for_download",
    )
    values.update(changes)
    return DowngradeOperation(**values)


def import_candidate(**changes):
    value = {
        "movie": {"id": 7}, "downloadId": "download-1",
        "path": "/downloads/Film.mkv", "size": 40,
        "quality": {"quality": {"name": "Bluray-1080p"}},
        "languages": [{"id": 1, "name": "English"}],
        "rejections": [{"reason": "Not an upgrade for existing movie file(s)", "type": "permanent"}],
    }
    value.update(changes)
    return value


class Phase2B2Tests(unittest.TestCase):
    def stores(self, directory):
        return (
            DowngradeSuppressionStore(Path(directory) / "suppressions.json"),
            DowngradeOperationStore(Path(directory) / "operations.json"),
        )

    def service(self, directory, candidates=None, record=None):
        suppressions, operations = self.stores(directory)
        operations.save(record or operation())
        radarr = Mock()
        radarr.get_manual_import_candidates.return_value = candidates or []
        return DowngradeOperationService(
            radarr, suppressions, operation_store=operations, timeout=0,
        ), operations, radarr

    def configured_submission(self):
        radarr = Mock()
        radarr.manual_search.return_value = [{
            "guid": "guid", "indexerId": 4, "releaseTitle": "Film.1080p",
            "size": 40, "protocol": "usenet",
        }]
        radarr.get_movie_file_snapshot.return_value = {
            "movie_id": 7, "movie_file_id": 70, "path": "/movies/Film.mkv",
            "size": 100, "quality": {"quality": {"name": "Bluray-2160p"}},
        }
        radarr.grab_release.return_value = {"downloadId": "download-1"}
        radarr.get_queue.return_value = []
        return radarr

    def test_operation_is_persisted_before_post_and_download_id_is_added(self):
        with tempfile.TemporaryDirectory() as directory:
            suppressions, operations = self.stores(directory)
            radarr = self.configured_submission()
            def grab(_):
                saved = DowngradeOperationStore(operations.state_file).get(7)
                self.assertEqual(saved.state, "submitting")
                self.assertEqual(saved.original_movie_file_id, 70)
                self.assertEqual(saved.original_file_path, "/movies/Film.mkv")
                self.assertEqual(saved.original_file_size, 100)
                self.assertEqual(saved.original_quality["quality"]["name"], "Bluray-2160p")
                return {"downloadId": "download-1"}
            radarr.grab_release.side_effect = grab
            DowngradeOperationService(radarr, suppressions, operation_store=operations, timeout=0).run(7, selected())
            reloaded = DowngradeOperationStore(operations.state_file).get(7)
            self.assertEqual(reloaded.download_id, "download-1")
            self.assertEqual(reloaded.state, "waiting_for_download")

    def test_definitive_rejection_clears_both_records_but_ambiguity_retains(self):
        with tempfile.TemporaryDirectory() as directory:
            for error, cleared in ((requests.HTTPError(response=Mock(status_code=400)), True), (requests.Timeout(), False), (requests.HTTPError(response=Mock(status_code=500)), False)):
                suppressions, operations = self.stores(directory)
                radarr = self.configured_submission(); radarr.grab_release.side_effect = error
                with self.assertRaises((RadarrRejected, requests.RequestException)):
                    DowngradeOperationService(radarr, suppressions, operation_store=operations).run(7, selected())
                self.assertEqual(operations.get(7) is None, cleared)
                self.assertEqual(suppressions.has_active(7), not cleared)
                suppressions.remove(7); operations.remove(7)

    def test_store_reload_validation_one_record_and_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operations.json"; store = DowngradeOperationStore(path)
            store.save(operation()); store.transition(7, "inspecting_import", "inspection started")
            self.assertEqual(DowngradeOperationStore(path).get(7).state, "inspecting_import")
            data = json.loads(path.read_text()); data["records"]["8"] = {"movie_id": 8}
            path.write_text(json.dumps(data))
            with self.assertRaises(DowngradeOperationStoreError):
                DowngradeOperationStore(path)
            path.write_text(json.dumps({"version": 1, "records": {"7": operation().to_dict()}}))
            names = []
            import tempfile as tempfile_module
            real = tempfile_module.NamedTemporaryFile
            with patch("services.downgrade_operation_store.tempfile.NamedTemporaryFile", side_effect=lambda *a, **kw: (lambda f: (names.append(f.name), f)[1])(real(*a, **kw))):
                store.transition(7, "inspecting_import", "atomic transition")
            self.assertTrue(names[0].endswith(".tmp")); self.assertFalse(Path(names[0]).exists())

    def test_store_loading_fails_closed_for_every_corruption_class(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operations.json"
            self.assertIsNone(DowngradeOperationStore(path).get(7))
            invalid_states = (
                "not json",
                json.dumps({"version": 2, "records": {}}),
                json.dumps({"version": 1, "records": []}),
                json.dumps({"version": 1, "records": {"7": {"movie_id": 7}}}),
                json.dumps({"version": 1, "records": {"8": operation().to_dict()}}),
            )
            for state in invalid_states:
                with self.subTest(state=state):
                    path.write_text(state)
                    with self.assertRaises(DowngradeOperationStoreError):
                        DowngradeOperationStore(path)
            with patch.object(Path, "read_text", side_effect=OSError("unreadable")):
                with self.assertRaises(DowngradeOperationStoreError):
                    DowngradeOperationStore(path)

    def test_corrupted_state_blocks_submission_before_reads_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            suppressions, operations = self.stores(directory)
            operations.state_file.write_text("corrupt")
            radarr = self.configured_submission()
            service = DowngradeOperationService(
                radarr, suppressions, operation_store=operations,
            )
            with self.assertRaises(DowngradeOperationStoreError):
                service.run(7, selected())
            radarr.manual_search.assert_not_called()
            radarr.get_movie_file_snapshot.assert_not_called()
            radarr.grab_release.assert_not_called()
            self.assertFalse(suppressions.has_active(7))

    def test_corrupted_state_blocks_candidate_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, radarr = self.service(directory)
            operations.state_file.write_text("corrupt")
            result = service.inspect_manual_import_readiness(7)
            self.assertEqual(result.state, "ambiguous")
            radarr.get_manual_import_candidates.assert_not_called()

    def test_suppression_failure_rolls_back_operation_before_post(self):
        with tempfile.TemporaryDirectory() as directory:
            suppressions, operations = self.stores(directory)
            radarr = self.configured_submission()
            suppressions.add = Mock(side_effect=OSError("disk full"))
            service = DowngradeOperationService(
                radarr, suppressions, operation_store=operations,
            )
            with self.assertRaises(OSError):
                service.run(7, selected())
            radarr.grab_release.assert_not_called()
            self.assertFalse(suppressions.has_active(7))
            self.assertIsNone(operations.get(7))

    def test_suppression_and_rollback_failure_still_never_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            suppressions, operations = self.stores(directory)
            radarr = self.configured_submission()
            suppressions.add = Mock(side_effect=OSError("disk full"))
            operations.remove = Mock(side_effect=OSError("rollback failed"))
            service = DowngradeOperationService(
                radarr, suppressions, operation_store=operations,
            )
            with self.assertLogs("media-butler", "ERROR"):
                with self.assertRaisesRegex(OSError, "disk full"):
                    service.run(7, selected())
            radarr.grab_release.assert_not_called()
            self.assertFalse(suppressions.has_active(7))
            self.assertIsNotNone(DowngradeOperationStore(operations.state_file).get(7))

    def test_operation_store_path_is_sibling_and_explicit_store_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            suppression_path = Path(directory) / "custom" / "suppressions.json"
            suppressions = DowngradeSuppressionStore(suppression_path)
            derived = DowngradeOperationService(Mock(), suppressions)
            self.assertEqual(
                derived.operations.state_file,
                suppression_path.parent / "downgrade_operations.json",
            )
            explicit = DowngradeOperationStore(Path(directory) / "explicit.json")
            supplied = DowngradeOperationService(
                Mock(), suppressions, operation_store=explicit,
            )
            self.assertIs(supplied.operations, explicit)

    def test_store_create_only_and_lifecycle_updates_preserve_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operations.json"
            store = DowngradeOperationStore(path)
            first = operation()
            store.save(first)
            original_bytes = path.read_bytes()
            with self.assertRaises(DuplicateDowngradeOperationError):
                store.save(operation(selected_release_guid="replacement"))
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertEqual(store.get(7).selected_release_guid, "guid")

            for field, value in (
                ("selected_release_guid", "replacement"),
                ("original_file_path", "/movies/other.mkv"),
                ("original_quality", {"quality": {"name": "other"}}),
                ("created_at", operation().created_at),
                ("updated_at", operation().updated_at),
            ):
                before = path.read_bytes()
                with self.subTest(field=field):
                    with self.assertRaises(ValueError):
                        store.update(7, **{field: value})
                    self.assertEqual(path.read_bytes(), before)

            store.transition(7, "inspecting_import", "inspection started")
            self.assertEqual(store.get(7).state, "inspecting_import")
            store.update(7, download_id="exact-download")
            self.assertEqual(store.get(7).download_id, "exact-download")
            store.update(7, last_safe_diagnostic_reason="safe diagnostic")
            self.assertEqual(
                store.get(7).last_safe_diagnostic_reason, "safe diagnostic"
            )

    def test_invalid_store_ids_never_load_or_mutate_integer_record(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DowngradeOperationStore(Path(directory) / "operations.json")
            store.save(operation(movie_id=1))
            original = store.state_file.read_bytes()
            for invalid_id in (True, False, 1.0, 7.0, "1", "7", 0, -1):
                for method, arguments in (
                    (store.get, (invalid_id,)),
                    (store.update, (invalid_id,)),
                    (store.transition, (invalid_id, "blocked", "invalid")),
                    (store.remove, (invalid_id,)),
                ):
                    with self.subTest(invalid_id=invalid_id, method=method.__name__):
                        with patch.object(store, "_load", wraps=store._load) as load:
                            with self.assertRaises(ValueError):
                                method(*arguments)
                            load.assert_not_called()
                        self.assertEqual(store.state_file.read_bytes(), original)
            self.assertEqual(store.get(1).movie_id, 1)

    def test_invalid_workflow_ids_do_no_downstream_work(self):
        for invalid_id in (True, False, 7.0, "7", 0, -7):
            with self.subTest(invalid_id=invalid_id):
                radarr = Mock(); suppressions = Mock(); discovery = Mock(); operations = Mock()
                service = DowngradeOperationService(
                    radarr, suppressions, discovery, operation_store=operations,
                )
                with self.assertRaises(ValueError):
                    service.run(invalid_id, selected())
                with self.assertRaises(ValueError):
                    service.inspect_manual_import_readiness(invalid_id)
                self.assertEqual(suppressions.method_calls, [])
                self.assertEqual(discovery.method_calls, [])
                self.assertEqual(operations.method_calls, [])
                self.assertEqual(radarr.method_calls, [])

    def test_snapshot_movie_id_requires_exact_positive_integer_identity(self):
        malformed_ids = (True, False, 7.0, "7", 0, -7, 8, None)
        for snapshot_id in malformed_ids:
            with self.subTest(snapshot_id=snapshot_id):
                radarr = Mock()
                radarr.get_movie_file_snapshot.return_value = {
                    "movie_id": snapshot_id, "movie_file_id": 70,
                    "path": "/movies/Film.mkv", "size": 100, "quality": None,
                }
                service = DowngradeOperationService(
                    radarr, Mock(), operation_store=Mock(),
                )
                with self.assertRaises(UnsafeOriginalMovieFile):
                    service._new_operation(7, selected())

    def assert_state(self, candidate, state, record=None):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, radarr = self.service(directory, [candidate], record)
            result = service.inspect_manual_import_readiness(7)
            self.assertEqual(result.state, state)
            self.assertEqual(operations.get(7).state, state)
            radarr.get_manual_import_candidates.assert_called_once()
            method_names = [call[0] for call in radarr.method_calls]
            self.assertNotIn("submit_manual_import_candidate", method_names)
            return result

    def test_exact_normalized_not_upgrade_is_ready(self):
        self.assert_state(import_candidate(rejections=["  nOt An UpGrAdE FoR ExIsTiNg MoViE FiLe(S)  "]), "manual_import_ready")

    def test_rejections_fail_closed(self):
        self.assert_state(import_candidate(rejections=["Not an upgrade for existing movie file(s)", "File is locked"]), "blocked")
        self.assert_state(import_candidate(rejections=["Not an upgrade"]), "blocked")
        candidate = import_candidate(); del candidate["rejections"]
        self.assert_state(candidate, "blocked")

    def test_candidate_identity_and_safety_fail_closed(self):
        cases = [
            import_candidate(movie={"id": 8}), import_candidate(downloadId="wrong"),
            import_candidate(path="/movies/Film.mkv"), import_candidate(path="downloads/Film.mkv"),
            import_candidate(size=0), import_candidate(size=100),
            import_candidate(quality=None), import_candidate(languages=[]),
        ]
        cases.extend(
            import_candidate(movie={"id": malformed_id})
            for malformed_id in (True, False, 7.0, "7", 0, -7, None)
        )
        for candidate in cases:
            with self.subTest(candidate=candidate): self.assert_state(candidate, "blocked")

    def test_no_download_id_prevents_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, radarr = self.service(directory, record=operation(download_id=None))
            self.assertEqual(service.inspect_manual_import_readiness(7).state, "ambiguous")
            radarr.get_manual_import_candidates.assert_not_called()

    def test_zero_multiple_and_no_rejection_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _ = self.service(directory)
            self.assertEqual(service.inspect_manual_import_readiness(7).state, "inspecting_import")
        with tempfile.TemporaryDirectory() as directory:
            service, _, _ = self.service(directory, [import_candidate(), import_candidate(path="/downloads/other.mkv")])
            self.assertEqual(service.inspect_manual_import_readiness(7).state, "blocked")
        self.assert_state(import_candidate(rejections=[]), "automatic_import_detected")
