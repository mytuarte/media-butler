import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from models.health_issue import HealthIssue
from services.pipeline_monitor_service import PipelineMonitorService
from services.registry import services
from services.sabnzbd_client import SabnzbdClient
from views.health_alert_view import HealthAlertView


class HealthMonitorService:
    STALL_THRESHOLD_MINUTES = 5
    RESOLUTION_GRACE_CYCLES = 2

    HEALTH_STATE_FILE = Path("data/health_alerts.json")

    def __init__(self):
        self.sabnzbd = SabnzbdClient()
        self.pipeline = PipelineMonitorService()

        self.forced_issues: list[HealthIssue] = []

        self.active_issues: dict[str, HealthIssue] = {}

        self.missing_issue_cycles: dict[str, int] = {}

        self.download_progress: dict[
            str,
            dict,
        ] = {}

        self.alert_messages: dict[
            str,
            dict,
        ] = self._load_alert_state()

        self._task = None
        self.running = False

    def start(self):
        if self.running:
            return

        self.running = True

        self._task = asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self):
        while self.running:
            try:
                issues = self.check()

                await self._process_issues(
                    issues,
                )

            except Exception as error:
                print(f"[Health Monitor] Error: {error}")

            await asyncio.sleep(60)

    def check(self) -> list[HealthIssue]:
        issues: list[HealthIssue] = []

        issues.extend(self.forced_issues)

        issues.extend(self._check_downloads())

        try:
            issues.extend(self.pipeline.check_movies())

        except Exception as error:
            print(f"[Health Monitor] Pipeline check failed: {error}")

        return issues

    def add_test_issue(
        self,
        issue: HealthIssue,
    ):
        self.forced_issues = [
            issue,
        ]

    def clear_test_issues(self):
        self.forced_issues = []

    async def _process_issues(
        self,
        issues: list[HealthIssue],
    ):
        current_titles = {issue.title for issue in issues}

        previous_titles = set(self.active_issues.keys())

        new_issues = [
            issue
            for issue in issues
            if issue.title not in previous_titles
            and issue.title not in self.alert_messages
        ]

        for issue in new_issues:
            await self._send_alert(issue)

        for title in list(self.alert_messages.keys()):
            if title not in current_titles:
                self.missing_issue_cycles[title] = (
                    self.missing_issue_cycles.get(
                        title,
                        0,
                    )
                    + 1
                )

                if self.missing_issue_cycles[title] >= self.RESOLUTION_GRACE_CYCLES:
                    await self._remove_alert(title)

                    self.missing_issue_cycles.pop(
                        title,
                        None,
                    )

            else:
                self.missing_issue_cycles.pop(
                    title,
                    None,
                )

        self.active_issues = {issue.title: issue for issue in issues}

    async def _send_alert(
        self,
        issue: HealthIssue,
    ):
        if services.discord is None:
            return

        embed = HealthAlertView.build(issue)

        message = await services.discord.send_health_alert(embed)

        self.alert_messages[issue.title] = {
            "message_id": message.id,
            "issue_type": issue.issue_type,
            "details": issue.details,
            "created_at": issue.created_at.isoformat(),
            "severity": issue.severity,
        }

        self._save_alert_state()

    async def _remove_alert(
        self,
        title: str,
    ):
        alert = self.alert_messages.pop(
            title,
            None,
        )

        if alert is None:
            return

        if services.discord is None:
            return

        await services.discord.delete_health_alert(alert["message_id"])

        self._save_alert_state()

    def _load_alert_state(self) -> dict[str, dict]:
        if not self.HEALTH_STATE_FILE.exists():
            return {}

        try:
            with open(
                self.HEALTH_STATE_FILE,
                "r",
            ) as file:
                data = json.load(file)

            migrated = {}

            for title, value in data.items():
                if isinstance(value, int):
                    migrated[title] = {
                        "message_id": value,
                        "issue_type": "unknown",
                        "details": "",
                        "created_at": datetime.now().isoformat(),
                        "severity": "warning",
                    }
                else:
                    migrated[title] = value

            return migrated

        except Exception as error:
            print(f"[Health Monitor] Failed to load alert state: {error}")

            return {}

    def _save_alert_state(self):
        try:
            self.HEALTH_STATE_FILE.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with open(
                self.HEALTH_STATE_FILE,
                "w",
            ) as file:
                json.dump(
                    self.alert_messages,
                    file,
                    indent=4,
                )

        except Exception as error:
            print(f"[Health Monitor] Failed to save alert state: {error}")

    def _check_downloads(self) -> list[HealthIssue]:
        issues: list[HealthIssue] = []

        try:
            queue = self.sabnzbd.get_queue()

        except Exception as error:
            now = datetime.now()

            issues.append(
                HealthIssue(
                    title="SABnzbd Offline",
                    issue_type="service",
                    details=("Unable to connect to SABnzbd.\n" f"Error: {error}"),
                    created_at=now,
                    severity="critical",
                )
            )

            return issues

        slots = queue.get(
            "queue",
            {},
        ).get(
            "slots",
            [],
        )

        print(f"[Health Monitor] SAB queue items: {len(slots)}")

        now = datetime.now()

        for slot in slots:
            name = slot.get(
                "filename",
                "Unknown Download",
            )

            status = slot.get(
                "status",
                "Unknown",
            )

            progress = int(
                slot.get(
                    "percentage",
                    0,
                )
            )

            self._track_progress(
                name,
                progress,
                now,
            )

            if status.lower() in {
                "paused",
                "failed",
                "stopped",
            }:
                issues.append(
                    HealthIssue(
                        title=name,
                        issue_type="download",
                        details=(f"Status: {status}\n" f"Progress: {progress}%"),
                        created_at=now,
                        severity="warning",
                    )
                )

            elif self._is_stalled(
                name,
                now,
            ):
                issues.append(
                    HealthIssue(
                        title=name,
                        issue_type="stalled_download",
                        details=(
                            "No progress detected for "
                            f"{self.STALL_THRESHOLD_MINUTES} minutes.\n"
                            f"Progress: {progress}%"
                        ),
                        created_at=now,
                        severity="warning",
                    )
                )

        return issues

    def _track_progress(
        self,
        name: str,
        progress: int,
        now: datetime,
    ):
        previous = self.download_progress.get(name)

        if previous is None:
            self.download_progress[name] = {
                "progress": progress,
                "last_changed": now,
            }

            return

        if previous["progress"] != progress:
            self.download_progress[name] = {
                "progress": progress,
                "last_changed": now,
            }

    def _is_stalled(
        self,
        name: str,
        now: datetime,
    ) -> bool:
        progress = self.download_progress.get(name)

        if progress is None:
            return False

        elapsed = now - progress["last_changed"]

        return elapsed >= timedelta(minutes=self.STALL_THRESHOLD_MINUTES)
