import asyncio

from models.health_issue import HealthIssue


class HealthMonitorService:
    def __init__(self):
        self.active_issues: dict[str, HealthIssue] = {}
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
                self.check()

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

        self._update_active_issues(issues)

        return issues

    def _check_downloads(self) -> list[HealthIssue]:
        """
        Check SAB/qBittorrent downloads.
        """

        return []

    def _update_active_issues(
        self,
        issues: list[HealthIssue],
    ):
        self.active_issues = {issue.title: issue for issue in issues}
