import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from models.health_issue import HealthIssue
from services.registry import services
from services.sabnzbd_client import SabnzbdClient
from views.health_alert_view import HealthAlertView


class HealthMonitorService:
    STALL_THRESHOLD_MINUTES = 5
    HEALTH_STATE_FILE = Path("data/health_alerts.json")

    def __init__(self):
        self.sabnzbd = SabnzbdClient()

        self.active_issues: dict[str, HealthIssue] = {}

        self.download_progress: dict[
            str,
            dict,
        ] = {}

        self.alert_messages: dict[
            str,
            int,
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

                await self._process_issues(issues)

            except Exception as error:
                print(f"[Health Monitor] Error: {error}")

            await asyncio.sleep(60)

    def check(self) -> list[HealthIssue]:
        """
        Runs all health checks.
        Returns current active issues.
        """

        issues: list[HealthIssue] = []

        issues.extend(self._check_downloads())

        if services.pipeline_monitor:
            try:
                issues.extend(services.pipeline_monitor.check_movies())

            except Exception as error:
                print(f"[Health Monitor] Pipeline check failed: {error}")

        return issues

    def _check_downloads(self) -> list[HealthIssue]:
        """
        Check SABnzbd downloads for problems.
        """

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
                            f"No progress detected for "
                            f"{self.STALL_THRESHOLD_MINUTES} minutes.\n"
                            f"Progress: {progress}%"
                        ),
                        created_at=now,
                        severity="warning",
                    )
                )

        return issues

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

        resolved_issues = set(self.alert_messages.keys()) - current_titles

        for issue in new_issues:
            await self._send_alert(issue)

        for title in resolved_issues:
            await self._remove_alert(title)

        self.active_issues = {issue.title: issue for issue in issues}

    async def _send_alert(
        self,
        issue: HealthIssue,
    ):
        if services.discord is None:
            return

        embed = HealthAlertView.build(issue)

        message = await services.discord.send_health_alert(embed)

        self.alert_messages[issue.title] = message.id

        self._save_alert_state()

    async def _remove_alert(
        self,
        title: str,
    ):
        message_id = self.alert_messages.pop(
            title,
            None,
        )

        if message_id is None:
            return

        if services.discord is None:
            return

        await services.discord.delete_health_alert(message_id)

        self._save_alert_state()

    def _load_alert_state(self) -> dict[str, int]:
        if not self.HEALTH_STATE_FILE.exists():
            return {}

        try:
            with open(
                self.HEALTH_STATE_FILE,
                "r",
            ) as file:
                data = json.load(file)

            return {title: int(message_id) for title, message_id in data.items()}

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
