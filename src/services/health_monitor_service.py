import asyncio
from datetime import datetime, timedelta

from models.health_issue import HealthIssue
from services.registry import services
from services.sabnzbd_client import SabnzbdClient
from views.health_alert_view import HealthAlertView


class HealthMonitorService:
    STALL_THRESHOLD_MINUTES = 5

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
        ] = {}

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

        return issues

    def _check_downloads(self) -> list[HealthIssue]:
        """
        Check SABnzbd downloads for problems.
        """

        issues: list[HealthIssue] = []

        queue = self.sabnzbd.get_queue()

        slots = queue.get("queue", {}).get("slots", [])

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

        new_issues = [issue for issue in issues if issue.title not in previous_titles]

        resolved_issues = previous_titles - current_titles

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
