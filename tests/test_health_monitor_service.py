import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config import Config
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
        services.discord = self.discord

    def tearDown(self):
        services.discord = self.previous_discord
        Config.MEDIA_ROOT = self.previous_media_root
        Config.STORAGE_WARNING_THRESHOLD_PERCENT = self.previous_warning_threshold
        Config.STORAGE_CRITICAL_THRESHOLD_PERCENT = self.previous_critical_threshold
        self.temporary_directory.cleanup()

    def create_monitor(self):
        monitor = HealthMonitorService()
        monitor.HEALTH_STATE_FILE = self.state_file
        monitor.alert_messages = monitor._load_alert_state()
        return monitor

    @staticmethod
    def issue(details="The download is paused."):
        return HealthIssue(
            title="Example Download",
            issue_type="download",
            details=details,
            created_at=datetime(2026, 7, 21, 12, 0),
        )

    def process(self, monitor, issues, successful_sources):
        monitor.successful_monitor_sources = successful_sources
        asyncio.run(monitor._process_issues(issues))

    def test_active_alert_is_reused_after_restart(self):
        initial_monitor = self.create_monitor()
        issue = self.issue()
        self.process(initial_monitor, [issue], {"downloads"})

        restarted_monitor = self.create_monitor()
        self.process(restarted_monitor, [issue], {"downloads"})

        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(
            restarted_monitor.alert_messages[issue.alert_key]["message_id"],
            101,
        )

    def test_alert_key_normalizes_issue_identity(self):
        issue = HealthIssue(
            title="  Example   Download  ",
            issue_type=" DOWNLOAD ",
            details="The download is paused.",
            created_at=datetime(2026, 7, 21, 12, 0),
        )

        self.assertEqual(issue.alert_key, "download:example download")

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

        self.process(monitor, [issue], {"downloads"})

        self.assertEqual(self.discord.sent, [])
        self.assertNotIn(issue.title, monitor.alert_messages)
        self.assertIn(issue.alert_key, monitor.alert_messages)

    def test_resolved_alert_is_removed_after_grace_cycles(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"downloads"})

        self.process(monitor, [], {"downloads"})
        self.assertEqual(self.discord.deleted, [])

        self.process(monitor, [], {"downloads"})
        self.assertEqual(self.discord.deleted, [101])
        self.assertEqual(monitor.alert_messages, {})

    def test_failed_check_does_not_resolve_existing_alert(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"downloads"})

        self.process(monitor, [], set())

        self.assertEqual(self.discord.deleted, [])
        self.assertEqual(
            monitor.alert_messages[issue.alert_key]["missing_cycles"],
            0,
        )

    def test_changed_active_alert_updates_its_existing_message(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"downloads"})

        self.process(
            monitor,
            [self.issue("The download remains paused.")],
            {"downloads"},
        )

        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(self.discord.updated[0][0], 101)

    def test_failed_alert_update_does_not_create_a_duplicate_message(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"downloads"})
        self.discord.update_result = None

        self.process(
            monitor,
            [self.issue("The download remains paused.")],
            {"downloads"},
        )

        self.assertEqual(len(self.discord.sent), 1)
        self.assertEqual(self.discord.updated[0][0], 101)

    def test_restart_preserves_pending_resolution_grace_cycle(self):
        monitor = self.create_monitor()
        issue = self.issue()
        self.process(monitor, [issue], {"downloads"})
        self.process(monitor, [], {"downloads"})

        restarted_monitor = self.create_monitor()
        self.process(restarted_monitor, [], {"downloads"})

        self.assertEqual(self.discord.deleted, [101])
        self.assertEqual(restarted_monitor.alert_messages, {})
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

    def test_successful_service_check_marks_only_its_source_healthy(self):
        monitor = self.create_monitor()

        with patch.object(monitor, "_check_downloads", return_value=([], False)), patch.object(
            monitor,
            "_check_storage",
            return_value=([], False),
        ), patch.object(monitor.pipeline, "check_movies", return_value=[]), patch.object(
            monitor.radarr,
            "test_connection",
        ), patch.object(monitor.sonarr, "test_connection"), patch.object(
            monitor.sabnzbd,
            "test_connection",
        ), patch.object(monitor.plex, "test_connection"):
            issues = monitor.check()

        self.assertEqual(issues, [])
        self.assertSetEqual(
            monitor.successful_monitor_sources,
            {
                monitor.PIPELINE_MONITOR_SOURCE,
                monitor.RADARR_MONITOR_SOURCE,
                monitor.SONARR_MONITOR_SOURCE,
                monitor.SABNZBD_MONITOR_SOURCE,
                monitor.PLEX_MONITOR_SOURCE,
            },
        )

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
            monitor, "_check_downloads", return_value=([], False)
        ), patch.object(monitor, "_check_storage", return_value=([], False)), patch.object(
            monitor.pipeline, "check_movies", return_value=[]
        ), patch.object(monitor.radarr, "test_connection"), patch.object(
            monitor.sonarr, "test_connection"
        ), patch.object(monitor.sabnzbd, "test_connection"), patch.object(
            monitor.plex,
            "test_connection",
            side_effect=[ConnectionError("connection refused"), None, None],
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
