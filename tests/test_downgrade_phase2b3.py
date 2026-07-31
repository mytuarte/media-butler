import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from models.downgrade import DowngradeOperation, DowngradeSuppression
from services.downgrade_operation_service import DowngradeOperationService
from services.downgrade_operation_store import DowngradeOperationStore
from services.downgrade_operation_store import MissingDowngradeOperationError
from services.downgrade_suppression_store import DowngradeSuppressionStore


def candidate():
    return {
        "movie": {"id": 7}, "downloadId": "download-1",
        "path": "/downloads/Film.mkv", "size": 40,
        "quality": {"quality": {"name": "Bluray-1080p"}},
        "languages": [{"id": 1, "name": "English"}],
        "rejections": ["Not an upgrade for existing movie file(s)"],
    }


def operation():
    return DowngradeOperation(
        movie_id=7, selected_release_name="Film.1080p",
        selected_release_guid="guid", selected_indexer_id=4,
        selected_release_size=40, selected_protocol="usenet",
        original_movie_file_id=70, original_file_path="/movies/Film.mkv",
        original_file_size=100,
        original_quality={"quality": {"name": "Bluray-2160p"}},
        state="manual_import_ready", download_id="download-1",
    )


class Phase2B3Tests(unittest.TestCase):
    def configured(self, directory):
        suppressions = DowngradeSuppressionStore(Path(directory) / "suppressions.json")
        operations = DowngradeOperationStore(Path(directory) / "operations.json")
        operations.save(operation())
        suppressions.add(DowngradeSuppression(
            7, "guid", "Film.1080p", 4, "download-1",
        ))
        radarr = Mock()
        radarr.get_manual_import_candidates.return_value = [candidate()]
        radarr.get_movie_file_snapshot.return_value = {
            "movie_id": 7, "movie_file_id": 70, "path": "/movies/Film.mkv",
            "size": 100, "quality": {"quality": {"name": "Bluray-2160p"}},
        }
        radarr.submit_manual_import_candidate.return_value = {"id": 91}
        return DowngradeOperationService(
            radarr, suppressions, operation_store=operations,
        ), operations, suppressions, radarr

    def test_submit_persists_identity_and_command_once_then_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, suppressions, radarr = self.configured(directory)
            result = service.execute_ready_manual_import(7)
            self.assertEqual(result.state, "manual_import_submitted")
            saved = DowngradeOperationStore(operations.state_file).get(7)
            self.assertEqual(saved.replacement_candidate_path, "/downloads/Film.mkv")
            self.assertEqual(saved.replacement_candidate_size, 40)
            self.assertEqual(saved.manual_import_command_id, 91)
            self.assertIsNotNone(saved.manual_import_submitted_at)

            service.execute_ready_manual_import(7)
            radarr.submit_manual_import_candidate.assert_called_once_with(
                candidate(), "download-1", 7,
            )
            radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
            radarr.get_movie_file_snapshot.return_value = {
                "movie_id": 7, "movie_file_id": 71,
                "path": "/movies/Film (1999)/Film.mkv", "size": 40,
                "quality": {"quality": {"name": " bluray-1080P "}},
            }
            verified = service.poll_manual_import_command(7)
            self.assertEqual(verified.state, "replacement_verified")
            self.assertEqual(verified.original_snapshot["movie_file_id"], 70)
            self.assertEqual(verified.replacement_snapshot["movie_file_id"], 71)
            self.assertTrue(suppressions.has_active(7))

    def test_definitive_and_ambiguous_submission_fail_closed(self):
        for error, expected in (
            (requests.HTTPError(response=Mock(status_code=400)), "manual_import_failed"),
            (requests.Timeout(), "ambiguous"),
            (requests.HTTPError(response=Mock(status_code=500)), "ambiguous"),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                service, operations, suppressions, radarr = self.configured(directory)
                radarr.submit_manual_import_candidate.side_effect = error
                self.assertEqual(service.execute_ready_manual_import(7).state, expected)
                self.assertIsNotNone(operations.get(7))
                self.assertTrue(suppressions.has_active(7))
                service.execute_ready_manual_import(7)
                radarr.submit_manual_import_candidate.assert_called_once()

    def test_set_once_fields_cannot_be_changed_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            _, operations, _, _ = self.configured(directory)
            operations.set_replacement_candidate(7, "/downloads/Film.mkv", 40, {"quality": {"name": "HD"}})
            operations.set_manual_import_command(7, 91, "2026-07-30T00:00:00+00:00")
            reloaded = DowngradeOperationStore(operations.state_file)
            with self.assertRaises(ValueError):
                reloaded.set_replacement_candidate(7, "/downloads/Other.mkv", 39, {"quality": {"name": "HD"}})
            with self.assertRaises(ValueError):
                reloaded.set_manual_import_command(7, 92, "2026-07-30T00:00:00+00:00")

    def test_pre_submit_freshness_and_identity_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _, _, radarr = self.configured(directory)
            radarr.get_manual_import_candidates.return_value = []
            self.assertEqual(
                service.execute_ready_manual_import(7).state,
                "inspecting_import",
            )
            radarr.get_manual_import_candidates.assert_called_once_with(
                "download-1", 7,
            )
            radarr.submit_manual_import_candidate.assert_not_called()
        cases = (
            {"movie_file_id": 72},
            {"path": "/movies/Other.mkv"},
            {"size": 101},
            {"quality": {"quality": {"name": "HDTV-2160p"}}},
        )
        for snapshot_change in cases:
            with self.subTest(snapshot_change=snapshot_change), tempfile.TemporaryDirectory() as directory:
                service, operations, _, radarr = self.configured(directory)
                radarr.get_movie_file_snapshot.return_value.update(snapshot_change)
                self.assertEqual(service.execute_ready_manual_import(7).state, "blocked")
                radarr.get_manual_import_candidates.assert_called_once()
                radarr.submit_manual_import_candidate.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.configured(directory)
            operations.set_replacement_candidate(
                7, "/downloads/First.mkv", 39, candidate()["quality"],
            )
            changed = candidate(); changed["path"] = "/downloads/Second.mkv"
            radarr.get_manual_import_candidates.return_value = [changed]
            self.assertEqual(service.execute_ready_manual_import(7).state, "blocked")
            radarr.submit_manual_import_candidate.assert_not_called()

    def test_missing_wrong_suppression_and_malformed_readiness_prevent_post(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _, suppressions, radarr = self.configured(directory)
            suppressions.remove(7)
            self.assertEqual(service.execute_ready_manual_import(7).state, "blocked")
            radarr.submit_manual_import_candidate.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            service, _, suppressions, radarr = self.configured(directory)
            suppressions.update_download_id(7, "wrong-download")
            self.assertEqual(service.execute_ready_manual_import(7).state, "blocked")
            radarr.submit_manual_import_candidate.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            service, _, _, radarr = self.configured(directory)
            radarr.get_manual_import_candidates.side_effect = ValueError("malformed")
            self.assertEqual(service.execute_ready_manual_import(7).state, "ambiguous")
            radarr.submit_manual_import_candidate.assert_not_called()

    def test_submission_uses_no_delete_or_direct_media_filesystem_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _, _, radarr = self.configured(directory)
            service.execute_ready_manual_import(7)
            method_names = [call[0] for call in radarr.method_calls]
            self.assertNotIn("delete", " ".join(method_names).casefold())
            radarr.submit_manual_import_candidate.assert_called_once_with(
                candidate(), "download-1", 7,
            )

    def submitted(self, directory):
        service, operations, suppressions, radarr = self.configured(directory)
        self.assertEqual(service.execute_ready_manual_import(7).state, "manual_import_submitted")
        radarr.reset_mock()
        return service, operations, suppressions, radarr

    def test_polling_active_failed_unknown_malformed_and_api_failure(self):
        for status in ("queued", "started", "running"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                service, operations, _, radarr = self.submitted(directory)
                radarr.get_command_status.return_value = {"id": 91, "status": status}
                self.assertEqual(service.poll_manual_import_command(7).state, "manual_import_submitted")
                self.assertEqual(operations.get(7).state, "manual_import_submitted")
                radarr.submit_manual_import_candidate.assert_not_called()
        for response in (
            {"id": 91, "status": "unknown"}, {"id": 91},
            {"id": 92, "status": "running"}, None,
        ):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                service, operations, _, radarr = self.submitted(directory)
                radarr.get_command_status.return_value = response
                self.assertEqual(service.poll_manual_import_command(7).state, "ambiguous")
                radarr.submit_manual_import_candidate.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            service, _, _, radarr = self.submitted(directory)
            radarr.get_command_status.side_effect = requests.ConnectionError()
            self.assertEqual(service.poll_manual_import_command(7).state, "ambiguous")
            radarr.submit_manual_import_candidate.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.submitted(directory)
            radarr.get_command_status.return_value = {"id": 91, "status": "failed"}
            self.assertEqual(service.poll_manual_import_command(7).state, "manual_import_failed")
            before = operations.state_file.read_bytes()
            radarr.reset_mock()
            self.assertEqual(service.poll_manual_import_command(7).state, "manual_import_failed")
            self.assertEqual(operations.state_file.read_bytes(), before)
            self.assertEqual(radarr.method_calls, [])

    def test_every_replacement_mismatch_fails_and_completion_is_not_success(self):
        mismatches = (
            {"movie_file_id": 70},
            {"path": "/movies/Film.mkv"},
            {"size": 39},
            {"quality": {"quality": {"name": "HDTV-1080p"}}},
            {"movie_id": None},
        )
        for change in mismatches:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                service, operations, _, radarr = self.submitted(directory)
                replacement = {
                    "movie_id": 7, "movie_file_id": 71,
                    "path": "/movies/New/Film.mkv", "size": 40,
                    "quality": candidate()["quality"],
                }
                replacement.update(change)
                radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
                radarr.get_movie_file_snapshot.return_value = replacement
                self.assertEqual(service.poll_manual_import_command(7).state, "ambiguous")
                self.assertNotEqual(operations.get(7).state, "replacement_verified")
                radarr.submit_manual_import_candidate.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.submitted(directory)
            radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
            radarr.get_movie_file_snapshot.return_value = None
            self.assertEqual(service.poll_manual_import_command(7).state, "ambiguous")
            self.assertNotEqual(operations.get(7).state, "replacement_verified")
        unsafe = operation()
        unsafe.replacement_candidate_size = 100
        unsafe.replacement_candidate_quality = candidate()["quality"]
        reason = DowngradeOperationService._replacement_mismatch(unsafe, {
            "movie_id": 7, "movie_file_id": 71, "path": "/movies/New.mkv",
            "size": 100, "quality": candidate()["quality"],
        })
        self.assertIn("not smaller", reason)

    def test_verified_identity_is_atomic_reloadable_and_poll_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, suppressions, radarr = self.submitted(directory)
            replacement = {
                "movie_id": 7, "movie_file_id": 71,
                "path": "/movies/New/Film.mkv", "size": 40,
                "quality": candidate()["quality"],
            }
            restarted_radarr = Mock()
            restarted_radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
            restarted_radarr.get_movie_file_snapshot.return_value = replacement
            restarted_submission = DowngradeOperationService(
                restarted_radarr, suppressions,
                operation_store=DowngradeOperationStore(operations.state_file),
            )
            self.assertEqual(
                restarted_submission.poll_manual_import_command(7).state,
                "replacement_verified",
            )
            saved = DowngradeOperationStore(operations.state_file).get(7)
            self.assertEqual(saved.final_replacement_movie_file_id, 71)
            self.assertEqual(saved.final_replacement_path, replacement["path"])
            self.assertEqual(saved.final_replacement_size, 40)
            self.assertEqual(saved.final_replacement_quality, candidate()["quality"])
            before = operations.state_file.read_bytes()
            restarted = DowngradeOperationService(
                Mock(), suppressions,
                operation_store=DowngradeOperationStore(operations.state_file),
            )
            again = restarted.poll_manual_import_command(7)
            self.assertEqual(again.state, "replacement_verified")
            self.assertEqual(operations.state_file.read_bytes(), before)
            self.assertEqual(restarted.radarr.method_calls, [])

    def test_verification_save_failure_leaves_no_timestamp_state_split(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.submitted(directory)
            radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
            radarr.get_movie_file_snapshot.return_value = {
                "movie_id": 7, "movie_file_id": 71, "path": "/movies/New.mkv",
                "size": 40, "quality": candidate()["quality"],
            }
            operations.transition(
                7, "verifying_replacement", "Command completed; verifying replacement",
            )
            with patch.object(operations, "_save", side_effect=OSError("disk full")):
                self.assertEqual(service._verify_replacement(7).state, "ambiguous")
            saved = DowngradeOperationStore(operations.state_file).get(7)
            self.assertEqual(saved.state, "verifying_replacement")
            self.assertIsNone(saved.replacement_verified_at)
            self.assertIsNone(saved.final_replacement_movie_file_id)

    def test_partial_legacy_verification_record_fails_closed_on_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            _, operations, _, _ = self.configured(directory)
            data = json.loads(operations.state_file.read_text())
            data["records"]["7"]["replacement_verified_at"] = "2026-07-30T00:00:00+00:00"
            operations.state_file.write_text(json.dumps(data))
            with self.assertRaises(Exception):
                DowngradeOperationStore(operations.state_file)

    def test_missing_set_once_targets_raise_explicit_store_error(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DowngradeOperationStore(Path(directory) / "operations.json")
            with self.assertRaises(MissingDowngradeOperationError):
                store.set_replacement_candidate(
                    7, "/downloads/Film.mkv", 40, candidate()["quality"],
                )
            with self.assertRaises(MissingDowngradeOperationError):
                store.set_manual_import_command(
                    7, 91, "2026-07-30T00:00:00+00:00",
                )
            with self.assertRaises(MissingDowngradeOperationError):
                store.save_verified_replacement(7, {
                    "movie_id": 7, "movie_file_id": 71,
                    "path": "/movies/New.mkv", "size": 40,
                    "quality": candidate()["quality"],
                }, "2026-07-30T00:00:00+00:00", "verified")

    def test_operation_disappearing_before_candidate_persistence_never_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.configured(directory)
            real_claim = operations.claim_manual_import_submission

            def remove_then_claim(*arguments):
                operations.remove(7)
                return real_claim(*arguments)

            operations.claim_manual_import_submission = Mock(side_effect=remove_then_claim)
            self.assertEqual(service.execute_ready_manual_import(7).state, "ambiguous")
            radarr.submit_manual_import_candidate.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.configured(directory)
            snapshot = radarr.get_movie_file_snapshot.return_value.copy()

            def remove_after_inspection(_movie_id):
                operations.remove(7)
                return snapshot

            radarr.get_movie_file_snapshot.side_effect = remove_after_inspection
            self.assertEqual(service.execute_ready_manual_import(7).state, "ambiguous")
            radarr.submit_manual_import_candidate.assert_not_called()

    def test_operation_disappearing_after_post_is_ambiguous_and_never_reposts(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.configured(directory)

            def remove_after_post(*_arguments):
                operations.remove(7)
                return {"id": 91}

            radarr.submit_manual_import_candidate.side_effect = remove_after_post
            self.assertEqual(service.execute_ready_manual_import(7).state, "ambiguous")
            self.assertEqual(service.execute_ready_manual_import(7).state, "blocked")
            radarr.submit_manual_import_candidate.assert_called_once()

    def test_operation_disappearing_before_verified_save_never_reports_success(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.submitted(directory)
            radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
            radarr.get_movie_file_snapshot.return_value = {
                "movie_id": 7, "movie_file_id": 71, "path": "/movies/New.mkv",
                "size": 40, "quality": candidate()["quality"],
            }
            real_save = operations.save_verified_replacement

            def remove_then_save(*arguments):
                operations.remove(7)
                return real_save(*arguments)

            operations.save_verified_replacement = Mock(side_effect=remove_then_save)
            self.assertEqual(service.poll_manual_import_command(7).state, "ambiguous")
            radarr.submit_manual_import_candidate.assert_not_called()

    def test_coerced_original_snapshot_identities_prevent_submission(self):
        for field in ("movie_id", "movie_file_id"):
            for invalid in (True, 7.0, "7", 0, -7, None):
                with self.subTest(field=field, invalid=invalid), tempfile.TemporaryDirectory() as directory:
                    service, _, _, radarr = self.configured(directory)
                    radarr.get_movie_file_snapshot.return_value[field] = invalid
                    self.assertEqual(service.execute_ready_manual_import(7).state, "blocked")
                    radarr.submit_manual_import_candidate.assert_not_called()

    def test_coerced_replacement_movie_ids_fail_verification(self):
        for invalid in (True, 7.0, "7", 0, -7, None):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                service, operations, _, radarr = self.submitted(directory)
                radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
                radarr.get_movie_file_snapshot.return_value = {
                    "movie_id": invalid, "movie_file_id": 71,
                    "path": "/movies/New.mkv", "size": 40,
                    "quality": candidate()["quality"],
                }
                self.assertEqual(service.poll_manual_import_command(7).state, "ambiguous")
                self.assertNotEqual(operations.get(7).state, "replacement_verified")

    def test_verified_store_rejects_coerced_movie_ids_without_writing(self):
        for invalid in (True, 7.0, "7", 0, -7, None):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                _, operations, _, _ = self.configured(directory)
                operations.set_replacement_candidate(
                    7, "/downloads/Film.mkv", 40, candidate()["quality"],
                )
                before = operations.state_file.read_bytes()
                with self.assertRaises(ValueError):
                    operations.save_verified_replacement(7, {
                        "movie_id": invalid, "movie_file_id": 71,
                        "path": "/movies/New.mkv", "size": 40,
                        "quality": candidate()["quality"],
                    }, "2026-07-30T00:00:00+00:00", "verified")
                self.assertEqual(operations.state_file.read_bytes(), before)

    def test_atomic_claim_failure_and_missing_claim_never_post(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.configured(directory)
            with patch.object(
                operations, "claim_manual_import_submission",
                side_effect=OSError("disk full"),
            ):
                self.assertEqual(service.execute_ready_manual_import(7).state, "ambiguous")
            radarr.submit_manual_import_candidate.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.configured(directory)
            real_claim = operations.claim_manual_import_submission

            def missing_claim(*arguments):
                operations.remove(7)
                return real_claim(*arguments)

            with patch.object(
                operations, "claim_manual_import_submission",
                side_effect=missing_claim,
            ):
                self.assertEqual(service.execute_ready_manual_import(7).state, "ambiguous")
            radarr.submit_manual_import_candidate.assert_not_called()

    def test_concurrent_services_issue_exactly_one_manual_import_post(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, suppressions, radarr = self.configured(directory)
            second = DowngradeOperationService(
                radarr,
                DowngradeSuppressionStore(suppressions.state_file),
                operation_store=DowngradeOperationStore(operations.state_file),
            )
            one_caller_finished = threading.Event()

            def delayed_post(*_arguments):
                one_caller_finished.wait(timeout=2)
                return {"id": 91}

            radarr.submit_manual_import_candidate.side_effect = delayed_post

            def execute(current):
                result = current.execute_ready_manual_import(7)
                one_caller_finished.set()
                return result

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(
                    execute,
                    (service, second),
                ))
            self.assertEqual(
                sum(result.state == "manual_import_submitted" for result in results),
                1,
            )
            self.assertIn(
                next(result.state for result in results if result.state != "manual_import_submitted"),
                {"submitting_manual_import", "manual_import_submitted", "ambiguous"},
            )
            radarr.submit_manual_import_candidate.assert_called_once_with(
                candidate(), "download-1", 7,
            )

    def test_concurrent_completed_pollers_share_one_verified_result(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, suppressions, radarr = self.submitted(directory)
            second_radarr = Mock()
            second = DowngradeOperationService(
                second_radarr,
                DowngradeSuppressionStore(suppressions.state_file),
                operation_store=DowngradeOperationStore(operations.state_file),
            )
            barrier = threading.Barrier(2)

            def completed(*_arguments):
                barrier.wait(timeout=2)
                return {"id": 91, "status": "completed"}

            replacement = {
                "movie_id": 7, "movie_file_id": 71,
                "path": "/movies/New/Film.mkv", "size": 40,
                "quality": candidate()["quality"],
            }
            radarr.get_command_status.side_effect = completed
            second_radarr.get_command_status.side_effect = completed
            radarr.get_movie_file_snapshot.return_value = replacement
            second_radarr.get_movie_file_snapshot.return_value = replacement
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(
                    lambda current: current.poll_manual_import_command(7),
                    (service, second),
                ))
            self.assertEqual(
                [result.state for result in results],
                ["replacement_verified", "replacement_verified"],
            )
            self.assertEqual(
                results[0].replacement_verified_at,
                results[1].replacement_verified_at,
            )
            before = operations.state_file.read_bytes()
            terminal = service.poll_manual_import_command(7)
            self.assertEqual(terminal.state, "replacement_verified")
            self.assertEqual(operations.state_file.read_bytes(), before)

    def test_verification_transition_failure_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, _, radarr = self.submitted(directory)
            radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
            with patch.object(
                operations, "transition_if_current",
                side_effect=OSError("disk full"),
            ):
                result = service.poll_manual_import_command(7)
            self.assertEqual(result.state, "ambiguous")
            radarr.submit_manual_import_candidate.assert_not_called()

    def test_concurrent_different_final_identity_fails_one_poller_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            service, operations, suppressions, radarr = self.submitted(directory)
            second_radarr = Mock()
            second = DowngradeOperationService(
                second_radarr,
                DowngradeSuppressionStore(suppressions.state_file),
                operation_store=DowngradeOperationStore(operations.state_file),
            )
            radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
            second_radarr.get_command_status.return_value = {"id": 91, "status": "completed"}
            snapshot_barrier = threading.Barrier(2)

            def snapshot(path):
                def get_snapshot(*_arguments):
                    snapshot_barrier.wait(timeout=2)
                    return {
                        "movie_id": 7, "movie_file_id": 71, "path": path,
                        "size": 40, "quality": candidate()["quality"],
                    }
                return get_snapshot

            radarr.get_movie_file_snapshot.side_effect = snapshot("/movies/New/Film.mkv")
            second_radarr.get_movie_file_snapshot.side_effect = snapshot("/movies/Other/Film.mkv")
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(
                    lambda current: current.poll_manual_import_command(7),
                    (service, second),
                ))
            self.assertEqual(
                [result.state for result in results],
                ["replacement_verified", "replacement_verified"],
            )
            saved = DowngradeOperationStore(operations.state_file).get(7)
            self.assertEqual(saved.state, "replacement_verified")

    def test_stale_command_outcomes_return_concurrent_verified_terminal(self):
        stale_outcomes = (
            {"id": 91, "status": "running"},
            {"id": 91, "status": "failed"},
            {"id": 91, "status": "unknown"},
            {"id": 92, "status": "running"},
            requests.ConnectionError("offline"),
        )
        for stale in stale_outcomes:
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as directory:
                winner, operations, suppressions, winner_radarr = self.submitted(directory)
                stale_radarr = Mock()
                stale_service = DowngradeOperationService(
                    stale_radarr,
                    DowngradeSuppressionStore(suppressions.state_file),
                    operation_store=DowngradeOperationStore(operations.state_file),
                )
                entered = threading.Event()
                verified = threading.Event()

                def stale_status(*_arguments):
                    entered.set()
                    verified.wait(timeout=2)
                    if isinstance(stale, Exception):
                        raise stale
                    return stale

                stale_radarr.get_command_status.side_effect = stale_status
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(stale_service.poll_manual_import_command, 7)
                    self.assertTrue(entered.wait(timeout=2))
                    winner_radarr.get_command_status.return_value = {
                        "id": 91, "status": "completed",
                    }
                    winner_radarr.get_movie_file_snapshot.return_value = {
                        "movie_id": 7, "movie_file_id": 71,
                        "path": "/movies/New.mkv", "size": 40,
                        "quality": candidate()["quality"],
                    }
                    winner_result = winner.poll_manual_import_command(7)
                    before = operations.state_file.read_bytes()
                    verified.set()
                    stale_result = future.result(timeout=2)
                self.assertEqual(winner_result.state, "replacement_verified")
                self.assertEqual(stale_result.state, "replacement_verified")
                self.assertEqual(operations.state_file.read_bytes(), before)
                stale_radarr.submit_manual_import_candidate.assert_not_called()

    def test_stale_bad_snapshot_returns_concurrent_verified_terminal(self):
        for stale_snapshot in (
            None,
            {
                "movie_id": 7, "movie_file_id": 70,
                "path": "/movies/Film.mkv", "size": 100,
                "quality": {"quality": {"name": "Wrong"}},
            },
        ):
            with self.subTest(snapshot=stale_snapshot), tempfile.TemporaryDirectory() as directory:
                winner, operations, suppressions, winner_radarr = self.submitted(directory)
                stale_radarr = Mock()
                stale_service = DowngradeOperationService(
                    stale_radarr,
                    DowngradeSuppressionStore(suppressions.state_file),
                    operation_store=DowngradeOperationStore(operations.state_file),
                )
                snapshot_entered = threading.Event()
                verified = threading.Event()

                def delayed_snapshot(*_arguments):
                    snapshot_entered.set()
                    verified.wait(timeout=2)
                    return stale_snapshot

                stale_radarr.get_command_status.return_value = {
                    "id": 91, "status": "completed",
                }
                stale_radarr.get_movie_file_snapshot.side_effect = delayed_snapshot
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(stale_service.poll_manual_import_command, 7)
                    self.assertTrue(snapshot_entered.wait(timeout=2))
                    winner_radarr.get_command_status.return_value = {
                        "id": 91, "status": "completed",
                    }
                    winner_radarr.get_movie_file_snapshot.return_value = {
                        "movie_id": 7, "movie_file_id": 71,
                        "path": "/movies/New.mkv", "size": 40,
                        "quality": candidate()["quality"],
                    }
                    self.assertEqual(
                        winner.poll_manual_import_command(7).state,
                        "replacement_verified",
                    )
                    before = operations.state_file.read_bytes()
                    verified.set()
                    stale_result = future.result(timeout=2)
                self.assertEqual(stale_result.state, "replacement_verified")
                self.assertEqual(operations.state_file.read_bytes(), before)

    def test_stale_completed_and_running_cannot_reopen_failed_terminal(self):
        for stale_status in ("completed", "running"):
            with self.subTest(status=stale_status), tempfile.TemporaryDirectory() as directory:
                winner, operations, suppressions, winner_radarr = self.submitted(directory)
                stale_radarr = Mock()
                stale_service = DowngradeOperationService(
                    stale_radarr,
                    DowngradeSuppressionStore(suppressions.state_file),
                    operation_store=DowngradeOperationStore(operations.state_file),
                )
                entered = threading.Event()
                failed = threading.Event()

                def delayed_status(*_arguments):
                    entered.set()
                    failed.wait(timeout=2)
                    return {"id": 91, "status": stale_status}

                stale_radarr.get_command_status.side_effect = delayed_status
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(stale_service.poll_manual_import_command, 7)
                    self.assertTrue(entered.wait(timeout=2))
                    winner_radarr.get_command_status.return_value = {
                        "id": 91, "status": "failed",
                    }
                    self.assertEqual(
                        winner.poll_manual_import_command(7).state,
                        "manual_import_failed",
                    )
                    before = operations.state_file.read_bytes()
                    failed.set()
                    stale_result = future.result(timeout=2)
                self.assertEqual(stale_result.state, "manual_import_failed")
                self.assertEqual(operations.state_file.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
