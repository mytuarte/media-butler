import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from models.health_issue import HealthIssue
from services.pipeline_monitor_service import PipelineMonitorService
from services.registry import services
from services.sabnzbd_client import SabnzbdClient


class HealthMonitorService:
    STALL_THRESHOLD_MINUTES = 5
    RESOLUTION_GRACE_CYCLES = 2

    DOWNLOADS_MONITOR_SOURCE = "downloads"
    PIPELINE_MONITOR_SOURCE = "pipeline"

    HEALTH_STATE_FILE = Path("data/health_alerts.json")

    def __init__(self):
        self.sabnzbd = SabnzbdClient()
        self.pipeline = PipelineMonitorService()

        self.forced_issues: list[HealthIssue] = []

        self.successful_monitor_sources: set[str] = set()

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

        self.successful_monitor_sources = set()

        download_issues, downloads_checked = self._check_downloads()
        issues.extend(download_issues)

        if downloads_checked:
            self.successful_monitor_sources.add(
                self.DOWNLOADS_MONITOR_SOURCE,
            )

        try:
            issues.extend(self.pipeline.check_movies())
            self.successful_monitor_sources.add(
                self.PIPELINE_MONITOR_SOURCE,
            )

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
        current_issues = {
            issue.alert_key: issue
            for issue in issues
        }

        for alert_key, issue in current_issues.items():
            alert = self._get_alert(alert_key, issue)

            if alert is None:
                await self._send_alert(alert_key, issue)
                continue

            if alert["missing_cycles"]:
                alert["missing_cycles"] = 0
                self._save_alert_state()

            if self._alert_changed(alert, issue):
                message_exists = await services.discord.update_health_alert(
                    alert["message_id"],
                    issue,
                )

                if message_exists is False:
                    await self._send_alert(alert_key, issue)
                    continue

                if message_exists is None:
                    continue

                self._update_alert(alert, issue)
                self._save_alert_state()

        for alert_key, alert in list(self.alert_messages.items()):
            if alert_key in current_issues:
                continue

            if alert["monitor_source"] not in self.successful_monitor_sources:
                continue

            alert["missing_cycles"] += 1

            if alert["missing_cycles"] >= self.RESOLUTION_GRACE_CYCLES:
                await self._remove_alert(alert_key)
            else:
                self._save_alert_state()

    async def _send_alert(
        self,
        alert_key: str,
        issue: HealthIssue,
    ):
        if services.discord is None:
            return

        message = await services.discord.send_health_alert(issue)

        self.alert_messages[alert_key] = {
            "message_id": message.id,
            "issue_type": issue.issue_type,
            "details": issue.details,
            "created_at": issue.created_at.isoformat(),
            "severity": issue.severity,
            "missing_cycles": 0,
            "monitor_source": self._monitor_source_for(issue),
        }

        self._save_alert_state()

    async def _remove_alert(
        self,
        alert_key: str,
    ):
        alert = self.alert_messages.get(alert_key)

        if alert is None:
            return

        if services.discord is None:
            return

        deleted = await services.discord.delete_health_alert(alert["message_id"])

        if not deleted:
            return

        self.alert_messages.pop(alert_key)

        self._save_alert_state()

    def _get_alert(
        self,
        alert_key: str,
        issue: HealthIssue,
    ) -> dict | None:
        alert = self.alert_messages.get(alert_key)

        if alert is not None:
            return alert

        legacy_alert = self.alert_messages.pop(issue.title, None)

        if legacy_alert is None:
            return None

        self.alert_messages[alert_key] = legacy_alert
        self._save_alert_state()

        return legacy_alert

    def _alert_changed(
        self,
        alert: dict,
        issue: HealthIssue,
    ) -> bool:
        return any(
            (
                alert[field] != value
                for field, value in {
                    "issue_type": issue.issue_type,
                    "details": issue.details,
                    "severity": issue.severity,
                }.items()
            )
        )

    def _monitor_source_for(
        self,
        issue: HealthIssue,
    ) -> str:
        if issue.issue_type == "pipeline":
            return self.PIPELINE_MONITOR_SOURCE

        return self.DOWNLOADS_MONITOR_SOURCE

    def _update_alert(
        self,
        alert: dict,
        issue: HealthIssue,
    ):
        alert.update(
            {
                "issue_type": issue.issue_type,
                "details": issue.details,
                "created_at": issue.created_at.isoformat(),
                "severity": issue.severity,
                "monitor_source": self._monitor_source_for(issue),
            }
        )

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
                        "missing_cycles": 0,
                        "monitor_source": "unknown",
                    }
                else:
                    value.setdefault("missing_cycles", 0)
                    value.setdefault(
                        "monitor_source",
                        self._monitor_source_from_issue_type(
                            value.get("issue_type", "unknown"),
                        ),
                    )
                    migrated[title] = value

            return migrated

        except Exception as error:
            print(f"[Health Monitor] Failed to load alert state: {error}")

            return {}

    def _monitor_source_from_issue_type(
        self,
        issue_type: str,
    ) -> str:
        if issue_type == "unknown":
            return "unknown"

        if issue_type == "pipeline":
            return self.PIPELINE_MONITOR_SOURCE

        return self.DOWNLOADS_MONITOR_SOURCE

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

    def _check_downloads(self) -> tuple[list[HealthIssue], bool]:
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

            return issues, False

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

        return issues, True

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
