import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from config import Config, _positive_int_config_value
from models.health_issue import HealthIssue
from services.health_monitor_service import HealthMonitorService
from services.registry import services


class FakeDiscordService:
    def __init__(self):
        self.sent = []
        self.updated = []
        self.deleted = []
        self.update_result = True

    async def send_health_alert(self, issue):
        self.sent.append(issue)
        return SimpleNamespace(id=100 + len(self.sent))

    async def update_health_alert(self, message_id, issue):
        self.updated.append((message_id, issue))
        return self.update_result

    async def delete_health_alert(self, message_id):
        self.deleted.append(message_id)
        return True


class HealthMonitorServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "health_alerts.json"
        self.discord = FakeDiscordService()
        self.previous_discord = services.discord
        self.previous_media_root = Config.MEDIA_ROOT
        self.previous_warning_threshold = Config.STORAGE_WARNING_THRESHOLD_PERCENT
        self.previous_critical_threshold = Config.STORAGE_CRITICAL_THRESHOLD_PERCENT
        self.previous_health_interval = Config.HEALTH_MONITOR_INTERVAL_SECONDS
        services.discord = self.discord

    def tearDown(self):
        services.discord = self.previous_discord
        Config.MEDIA_ROOT = self.previous_media_root
        Config.STORAGE_WARNING_THRESHOLD_PERCENT = self.previous_warning_threshold
        Config.STORAGE_CRITICAL_THRESHOLD_PERCENT = self.previous_critical_threshold
        Config.HEALTH_MONITOR_INTERVAL_SECONDS = self.previous_health_interval
        self.temporary_directory.cleanup()

    def create_monitor(self):
        monitor = HealthMonitorService()
        monitor.HEALTH_STATE_FILE = self.state_file
        monitor.alert_messages = monitor._load_alert_state()
        return monitor

    @staticmethod
    def issue(details="Unable to connect to SABnzbd."):
        return HealthIssue(
            title="SABnzbd Offline",
            issue_type="service",
            details=details,
            created_at=datetime(2026, 7, 21, 12, 0),
            severity="critical",
            monitor_source=HealthMonitorService.SABNZBD_MONITOR_SOURCE,
        )

    def process(self, monitor, issues, successful_sources):
        monitor.successful_monitor_sources = successful_sources
        asyncio.run(monitor._process_issues(issues))

    def test_active_alert_is_reused_after_restart(self):
        initial_monitor = self.create_monitor()
        issue = self.issue()
        self.process(initial_monitor, [issue], {"sabnzbd"})

        restarted_monitor = self.create_monitor()
        self.process(restarted_monitor, [issue], {"sabnzbd"})

        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(
            restarted_monitor.alert_messages[issue.alert_key]["message_id"],
            101,
        )

    def test_alert_key_normalizes_issue_identity(self):
        issue = HealthIssue(
            title="  SABnzbd   Offline  ",
            issue_type=" SERVICE ",
            details="Unable to connect to SABnzbd.",
            created_at=datetime(2026, 7, 21, 12, 0),
        )

        self.assertEqual(issue.alert_key, "service:sabnzbd offline")

    def test_existing_title_key_is_migrated_without_a_duplicate_alert(self):
        issue = self.issue()
        self.state_file.write_text(
            json.dumps(
                {
                    issue.title: {
                        "message_id": 101,
                        "issue_type": issue.issue_type,
                        "details": issue.details,
                        "created_at": issue.created_at.isoformat(),
                        "severity": issue.severity,
                    }
                }
            )
        )
        monitor = self.create_monitor()

        self.process(monitor, [issue], {"sabnzbd"})

        self.assertEqual(self.discord.sent, [])
        self.assertNotIn(issue.title, monitor.alert_messages)
        self.assertIn(issue.alert_key, monitor.alert_messages)

    def test_resolved_alert_is_removed_after_grace_cycles(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"sabnzbd"})

        self.process(monitor, [], {"sabnzbd"})
        self.assertEqual(self.discord.deleted, [])

        self.process(monitor, [], {"sabnzbd"})
        self.assertEqual(self.discord.deleted, [101])
        self.assertEqual(monitor.alert_messages, {})

    def test_failed_check_does_not_resolve_existing_alert(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"sabnzbd"})

        self.process(monitor, [], set())

        self.assertEqual(self.discord.deleted, [])
        self.assertEqual(
            monitor.alert_messages[issue.alert_key]["missing_cycles"],
            0,
        )

    def test_changed_active_alert_updates_its_existing_message(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"sabnzbd"})

        self.process(
            monitor,
            [self.issue("SABnzbd remains unavailable.")],
            {"sabnzbd"},
        )

        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(self.discord.updated[0][0], 101)

    def test_failed_alert_update_does_not_create_a_duplicate_message(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"sabnzbd"})
        self.discord.update_result = None

        self.process(
            monitor,
            [self.issue("SABnzbd remains unavailable.")],
            {"sabnzbd"},
        )

        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(self.discord.updated[0][0], 101)

    def test_restart_preserves_pending_resolution_grace_cycle(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"sabnzbd"})
        self.process(monitor, [], {"sabnzbd"})

        restarted_monitor = self.create_monitor()
        self.process(restarted_monitor, [], {"sabnzbd"})

        self.assertEqual(self.discord.deleted, [101])
        self.assertEqual(restarted_monitor.alert_messages, {})
        self.assertEqual(json.loads(self.state_file.read_text()), {})

    def test_paused_queue_item_does_not_create_a_health_alert(self):
        monitor = self.create_monitor()
        monitor.sabnzbd.get_queue = lambda: {
            "queue": {
                "slots": [
                    {
                        "filename": "The.Iron.Giant.1999.2160p.BluRay.mkv",
                        "status": "Paused",
                        "percentage": "99",
                    }
                ]
            }
        }

        issues, checked = monitor._check_sab_queue()

        self.assertTrue(checked)
        self.assertEqual(issues, [])

    def test_stalled_queue_item_does_not_create_a_health_alert(self):
        monitor = self.create_monitor()
        monitor.sabnzbd.get_queue = lambda: {
            "queue": {
                "slots": [
                    {
                        "filename": "The.Iron.Giant.1999.2160p.BluRay.mkv",
                        "status": "Downloading",
                        "percentage": "99",
                    }
                ]
            }
        }

        first_issues, first_checked = monitor._check_sab_queue()
        second_issues, second_checked = monitor._check_sab_queue()

        self.assertTrue(first_checked)
        self.assertTrue(second_checked)
        self.assertEqual(first_issues, [])
        self.assertEqual(second_issues, [])

    def test_queue_item_title_never_becomes_a_health_issue(self):
        monitor = self.create_monitor()
        release_title = "The.Iron.Giant.1999.2160p.BluRay.REMUX.mkv"
        monitor.sabnzbd.get_queue = lambda: {
            "queue": {
                "slots": [
                    {
                        "filename": release_title,
                        "status": "Failed",
                        "percentage": "42",
                    }
                ]
            }
        }

        issues, checked = monitor._check_sab_queue()

        self.assertTrue(checked)
        self.assertFalse(any(issue.title == release_title for issue in issues))

    def test_sab_queue_connection_failure_creates_service_health_issue(self):
        monitor = self.create_monitor()
        monitor.sabnzbd.get_queue = lambda: (_ for _ in ()).throw(
            ConnectionError("connection refused")
        )

        issues, checked = monitor._check_sab_queue()

        self.assertFalse(checked)
        self.assertEqual(issues[0].title, "SABnzbd Offline")
        self.assertEqual(issues[0].monitor_source, monitor.SABNZBD_MONITOR_SOURCE)
        self.assertIn("connection refused", issues[0].details)

    def test_sab_queue_timeout_creates_service_health_issue(self):
        monitor = self.create_monitor()
        monitor.sabnzbd.get_queue = lambda: (_ for _ in ()).throw(
            TimeoutError("request timed out")
        )

        issues, checked = monitor._check_sab_queue()

        self.assertFalse(checked)
        self.assertEqual(issues[0].title, "SABnzbd Offline")
        self.assertIn("request timed out", issues[0].details)

    def test_sab_queue_authentication_failure_creates_service_health_issue(self):
        monitor = self.create_monitor()
        monitor.sabnzbd.get_queue = lambda: (_ for _ in ()).throw(
            PermissionError("invalid API key")
        )

        issues, checked = monitor._check_sab_queue()

        self.assertFalse(checked)
        self.assertEqual(issues[0].title, "SABnzbd Offline")
        self.assertIn("invalid API key", issues[0].details)

    def test_healthy_sab_queue_avoids_service_health_issues(self):
        monitor = self.create_monitor()
        monitor.sabnzbd.get_queue = lambda: {"queue": {"slots": []}}

        issues, checked = monitor._check_sab_queue()

        self.assertTrue(checked)
        self.assertEqual(issues, [])

    def test_sab_queue_count_is_debug(self):
        monitor = self.create_monitor()
        monitor.sabnzbd.get_queue = lambda: {"queue": {"slots": [{}, {}]}}

        with self.assertLogs("media-butler", level="DEBUG") as logs:
            issues, checked = monitor._check_sab_queue()

        self.assertTrue(checked)
        self.assertEqual(issues, [])
        self.assertIn(
            "DEBUG:media-butler:[Health Monitor] SAB queue items: 2",
            "\n".join(logs.output),
        )

    def test_persisted_item_level_alerts_are_retired(self):
        self.state_file.write_text(
            json.dumps(
                {
                    "download:the iron giant": {
                        "message_id": 101,
                        "issue_type": "download",
                        "details": "Status: Paused",
                        "created_at": datetime.now().isoformat(),
                        "severity": "warning",
                        "monitor_source": "downloads",
                    }
                }
            )
        )

        monitor = self.create_monitor()

        self.assertEqual(monitor.alert_messages, {})

    def test_persisted_pipeline_alert_is_retired_after_grace_cycles(self):
        self.state_file.write_text(
            json.dumps(
                {
                    "pipeline:the iron giant": {
                        "message_id": 101,
                        "issue_type": "pipeline",
                        "details": "Movie appears stalled.",
                        "created_at": datetime.now().isoformat(),
                        "severity": "warning",
                        "monitor_source": "pipeline",
                    }
                }
            )
        )

        monitor = self.create_monitor()

        self.assertEqual(
            monitor.alert_messages["pipeline:the iron giant"]["monitor_source"],
            monitor.RETIRED_PIPELINE_MONITOR_SOURCE,
        )

        self.process(monitor, [], set())
        self.assertEqual(self.discord.deleted, [])

        self.process(monitor, [], set())

        self.assertEqual(self.discord.deleted, [101])
        self.assertEqual(monitor.alert_messages, {})
        self.assertEqual(json.loads(self.state_file.read_text()), {})

    def test_storage_check_creates_warning_with_configured_path_details(self):
        monitor = self.create_monitor()
        Config.MEDIA_ROOT = self.temporary_directory.name
        Config.STORAGE_WARNING_THRESHOLD_PERCENT = 15
        Config.STORAGE_CRITICAL_THRESHOLD_PERCENT = 5

        with patch(
            "services.health_monitor_service.shutil.disk_usage",
            return_value=(1000, 900, 100),
        ):
            issues, checked = monitor._check_storage()

        self.assertTrue(checked)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "warning")
        self.assertEqual(
            issues[0].details,
            "\n".join(
                [
                    f"Monitored Path: {Path(Config.MEDIA_ROOT)}",
                    "Total Capacity: 1000.0 B",
                    "Available Capacity: 100.0 B",
                    "Available Percentage: 10.0%",
                ]
            ),
        )

    def test_storage_check_creates_critical_issue_before_warning(self):
        monitor = self.create_monitor()
        Config.MEDIA_ROOT = self.temporary_directory.name
        Config.STORAGE_WARNING_THRESHOLD_PERCENT = 15
        Config.STORAGE_CRITICAL_THRESHOLD_PERCENT = 5

        with patch(
            "services.health_monitor_service.shutil.disk_usage",
            return_value=(1000, 960, 40),
        ):
            issues, checked = monitor._check_storage()

        self.assertTrue(checked)
        self.assertEqual(issues[0].severity, "critical")

    def test_storage_check_requires_an_existing_configured_media_root(self):
        monitor = self.create_monitor()
        Config.MEDIA_ROOT = None

        with patch("services.health_monitor_service.shutil.disk_usage") as disk_usage:
            issues, checked = monitor._check_storage()

        self.assertEqual(issues, [])
        self.assertFalse(checked)
        disk_usage.assert_not_called()

        Config.MEDIA_ROOT = str(Path(self.temporary_directory.name) / "missing")

        with patch("services.health_monitor_service.shutil.disk_usage") as disk_usage:
            issues, checked = monitor._check_storage()

        self.assertEqual(issues, [])
        self.assertFalse(checked)
        disk_usage.assert_not_called()

    def test_storage_check_is_healthy_at_the_warning_threshold(self):
        monitor = self.create_monitor()
        Config.MEDIA_ROOT = self.temporary_directory.name
        Config.STORAGE_WARNING_THRESHOLD_PERCENT = 15
        Config.STORAGE_CRITICAL_THRESHOLD_PERCENT = 5

        with patch(
            "services.health_monitor_service.shutil.disk_usage",
            return_value=(1000, 850, 150),
        ):
            issues, checked = monitor._check_storage()

        self.assertTrue(checked)
        self.assertEqual(issues, [])

    def test_service_availability_failure_creates_critical_issue(self):
        monitor = self.create_monitor()

        issues, checked = monitor._check_service_availability(
            "Plex",
            monitor.PLEX_MONITOR_SOURCE,
            lambda: (_ for _ in ()).throw(ConnectionError("Unauthorized")),
        )

        self.assertFalse(checked)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].title, "Plex unavailable")
        self.assertEqual(issues[0].issue_type, "service")
        self.assertEqual(issues[0].severity, "critical")
        self.assertEqual(issues[0].monitor_source, monitor.PLEX_MONITOR_SOURCE)

    def test_successful_service_check_marks_only_its_sources_healthy(self):
        monitor = self.create_monitor()

        with patch.object(
            monitor, "_check_sab_queue", return_value=([], False)
        ), patch.object(
            monitor,
            "_check_storage",
            return_value=([], False),
        ), patch.object(
            monitor.radarr,
            "test_connection",
        ), patch.object(
            monitor.sonarr, "test_connection"
        ), patch.object(
            monitor.sabnzbd,
            "test_connection",
        ), patch.object(
            monitor.plex, "test_connection"
        ), patch.object(
            monitor.overseerr, "test_connection"
        ):
            issues = monitor.check()

        self.assertEqual(issues, [])
        self.assertFalse(hasattr(monitor, "pipeline"))
        self.assertFalse(any(issue.issue_type == "pipeline" for issue in issues))
        self.assertSetEqual(
            monitor.successful_monitor_sources,
            {
                monitor.RADARR_MONITOR_SOURCE,
                monitor.SONARR_MONITOR_SOURCE,
                monitor.SABNZBD_MONITOR_SOURCE,
                monitor.PLEX_MONITOR_SOURCE,
                monitor.OVERSEERR_MONITOR_SOURCE,
            },
        )

    def test_overseerr_failure_creates_critical_availability_issue(self):
        monitor = self.create_monitor()

        issues, checked = monitor._check_service_availability(
            "Overseerr",
            monitor.OVERSEERR_MONITOR_SOURCE,
            lambda: (_ for _ in ()).throw(PermissionError("invalid API key")),
        )

        self.assertFalse(checked)
        self.assertEqual(issues[0].title, "Overseerr unavailable")
        self.assertEqual(issues[0].issue_type, "service")
        self.assertEqual(issues[0].severity, "critical")
        self.assertEqual(issues[0].monitor_source, "overseerr")

    def test_successful_overseerr_check_marks_only_overseerr_healthy(self):
        monitor = self.create_monitor()

        with patch.object(
            monitor, "_check_sab_queue", return_value=([], False)
        ), patch.object(
            monitor, "_check_storage", return_value=([], False)
        ), patch.object(
            monitor.radarr,
            "test_connection",
            side_effect=ConnectionError("unavailable"),
        ), patch.object(
            monitor.sonarr,
            "test_connection",
            side_effect=ConnectionError("unavailable"),
        ), patch.object(
            monitor.sabnzbd,
            "test_connection",
            side_effect=ConnectionError("unavailable"),
        ), patch.object(
            monitor.plex,
            "test_connection",
            side_effect=ConnectionError("unavailable"),
        ), patch.object(monitor.overseerr, "test_connection"):
            monitor.check()

        self.assertSetEqual(
            monitor.successful_monitor_sources,
            {monitor.OVERSEERR_MONITOR_SOURCE},
        )

    def test_overseerr_outage_does_not_stop_other_service_checks(self):
        monitor = self.create_monitor()

        with patch.object(
            monitor, "_check_sab_queue", return_value=([], False)
        ), patch.object(
            monitor, "_check_storage", return_value=([], False)
        ), patch.object(
            monitor.radarr, "test_connection"
        ) as radarr_check, patch.object(
            monitor.sonarr, "test_connection"
        ) as sonarr_check, patch.object(
            monitor.sabnzbd, "test_connection"
        ) as sabnzbd_check, patch.object(
            monitor.plex, "test_connection"
        ) as plex_check, patch.object(
            monitor.overseerr,
            "test_connection",
            side_effect=ConnectionError("connection refused"),
        ):
            issues = monitor.check()

        self.assertEqual([issue.title for issue in issues], ["Overseerr unavailable"])
        for check in (radarr_check, sonarr_check, sabnzbd_check, plex_check):
            check.assert_called_once_with()

    def test_overseerr_alert_resolves_after_successful_grace_cycles(self):
        monitor = self.create_monitor()
        issue = HealthIssue(
            title="Overseerr unavailable",
            issue_type="service",
            details="Unable to connect to Overseerr.\nError: invalid API key",
            created_at=datetime(2026, 7, 21, 12, 0),
            severity="critical",
            monitor_source=monitor.OVERSEERR_MONITOR_SOURCE,
        )

        self.process(monitor, [issue], set())
        self.process(monitor, [], {monitor.OVERSEERR_MONITOR_SOURCE})
        self.assertEqual(self.discord.deleted, [])

        self.process(monitor, [], {monitor.OVERSEERR_MONITOR_SOURCE})

        self.assertEqual(self.discord.deleted, [101])

    def test_health_monitor_interval_defaults_to_60_seconds(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                _positive_int_config_value("HEALTH_MONITOR_INTERVAL_SECONDS", "60"),
                60,
            )

    def test_health_monitor_loop_uses_configured_interval(self):
        monitor = self.create_monitor()
        Config.HEALTH_MONITOR_INTERVAL_SECONDS = 17
        monitor.running = True

        def check_once():
            monitor.running = False
            return []

        monitor.check = check_once
        with patch.object(
            monitor, "_process_issues", new_callable=AsyncMock
        ), patch(
            "services.health_monitor_service.asyncio.sleep", new_callable=AsyncMock
        ) as sleep:
            asyncio.run(monitor._monitor_loop())

        sleep.assert_awaited_once_with(17)

    def test_health_monitor_interval_requires_a_positive_integer(self):
        for invalid_value in ("invalid", "0", "-1"):
            with self.subTest(invalid_value=invalid_value), patch.dict(
                "os.environ",
                {"HEALTH_MONITOR_INTERVAL_SECONDS": invalid_value},
            ):
                with self.assertRaises(ValueError):
                    _positive_int_config_value("HEALTH_MONITOR_INTERVAL_SECONDS", "60")

    def test_service_alert_resolves_only_after_successful_checks(self):
        monitor = self.create_monitor()
        issue = HealthIssue(
            title="Plex unavailable",
            issue_type="service",
            details="Unable to connect to Plex.\nError: Unauthorized",
            created_at=datetime(2026, 7, 21, 12, 0),
            severity="critical",
            monitor_source=monitor.PLEX_MONITOR_SOURCE,
        )

        self.process(monitor, [issue], set())
        self.process(monitor, [], set())
        self.assertEqual(self.discord.deleted, [])

        self.process(monitor, [], {monitor.PLEX_MONITOR_SOURCE})
        self.assertEqual(self.discord.deleted, [])

        self.process(monitor, [], {monitor.PLEX_MONITOR_SOURCE})
        self.assertEqual(self.discord.deleted, [101])

    def test_plex_outage_creates_one_alert_and_recovery_resolves_it(self):
        monitor = self.create_monitor()

        with patch.object(
            monitor, "_check_sab_queue", return_value=([], False)
        ), patch.object(
            monitor, "_check_storage", return_value=([], False)
        ), patch.object(
            monitor.radarr, "test_connection"
        ), patch.object(
            monitor.sonarr, "test_connection"
        ), patch.object(
            monitor.sabnzbd, "test_connection"
        ), patch.object(
            monitor.plex,
            "test_connection",
            side_effect=[ConnectionError("connection refused"), None, None],
        ), patch.object(
            monitor.overseerr, "test_connection"
        ):
            issues = monitor.check()
            self.process(monitor, issues, monitor.successful_monitor_sources)

            self.assertEqual(len(self.discord.sent), 1)
            self.assertEqual(self.discord.sent[0].title, "Plex unavailable")
            self.assertIn("connection refused", self.discord.sent[0].details)

            issues = monitor.check()
            self.process(monitor, issues, monitor.successful_monitor_sources)
            self.assertEqual(len(self.discord.sent), 1)
            self.assertEqual(self.discord.deleted, [])

            issues = monitor.check()
            self.process(monitor, issues, monitor.successful_monitor_sources)

        self.assertEqual(self.discord.deleted, [101])


if __name__ == "__main__":
    unittest.main()
