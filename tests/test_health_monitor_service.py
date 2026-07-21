import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

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
        services.discord = self.discord

    def tearDown(self):
        services.discord = self.previous_discord
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


if __name__ == "__main__":
    unittest.main()
