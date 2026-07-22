import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path

from config import Config
from models.health_issue import HealthIssue
from services.pipeline_monitor_service import PipelineMonitorService
from services.plex_service import PlexService
from services.log_service import logger
from services.radarr_service import RadarrService
from services.registry import services
from services.sabnzbd_client import SabnzbdClient
from services.sonarr_service import SonarrService
from utils.formatting import format_size


class HealthMonitorService:
    RESOLUTION_GRACE_CYCLES = 2

    PIPELINE_MONITOR_SOURCE = "pipeline"
    STORAGE_MONITOR_SOURCE = "storage"
    RADARR_MONITOR_SOURCE = "radarr"
    SONARR_MONITOR_SOURCE = "sonarr"
    SABNZBD_MONITOR_SOURCE = "sabnzbd"
    PLEX_MONITOR_SOURCE = "plex"

    HEALTH_STATE_FILE = Path("data/health_alerts.json")

    def __init__(self):
        self.sabnzbd = SabnzbdClient()
        self.radarr = RadarrService()
        self.sonarr = SonarrService()
        self.plex = PlexService()
        self.pipeline = PipelineMonitorService()

        self.forced_issues: list[HealthIssue] = []

        self.successful_monitor_sources: set[str] = set()

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

        sab_queue_issues, sab_queue_checked = self._check_sab_queue()
        issues.extend(sab_queue_issues)

        if sab_queue_checked:
            self.successful_monitor_sources.add(
                self.SABNZBD_MONITOR_SOURCE,
            )

        storage_issues, storage_checked = self._check_storage()
        issues.extend(storage_issues)

        if storage_checked:
            self.successful_monitor_sources.add(
                self.STORAGE_MONITOR_SOURCE,
            )

        for service_name, monitor_source, check in (
            ("Radarr", self.RADARR_MONITOR_SOURCE, self.radarr.test_connection),
            ("Sonarr", self.SONARR_MONITOR_SOURCE, self.sonarr.test_connection),
            ("SABnzbd", self.SABNZBD_MONITOR_SOURCE, self.sabnzbd.test_connection),
            ("Plex", self.PLEX_MONITOR_SOURCE, self.plex.test_connection),
        ):
            service_issues, service_checked = self._check_service_availability(
                service_name,
                monitor_source,
                check,
            )
            issues.extend(service_issues)

            if service_checked:
                self.successful_monitor_sources.add(monitor_source)

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

    def _check_service_availability(
        self,
        service_name: str,
        monitor_source: str,
        check,
    ) -> tuple[list[HealthIssue], bool]:
        try:
            check()
        except Exception as error:
            print(f"[Health Monitor] {service_name} check failed: {error}")

            title = (
                "Plex unavailable"
                if monitor_source == self.PLEX_MONITOR_SOURCE
                else f"{service_name} Offline"
            )

            return [
                HealthIssue(
                    title=title,
                    issue_type="service",
                    details=(
                        f"Unable to connect to {service_name}.\n" f"Error: {error}"
                    ),
                    created_at=datetime.now(),
                    severity="critical",
                    monitor_source=monitor_source,
                )
            ], False

        return [], True

    async def _process_issues(
        self,
        issues: list[HealthIssue],
    ):
        current_issues = {issue.alert_key: issue for issue in issues}

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
        if issue.monitor_source is not None:
            return issue.monitor_source

        if issue.issue_type == "pipeline":
            return self.PIPELINE_MONITOR_SOURCE

        if issue.issue_type == "storage":
            return self.STORAGE_MONITOR_SOURCE

        return self.SABNZBD_MONITOR_SOURCE

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
                    if self._is_obsolete_download_alert(value):
                        continue

                    migrated[title] = value

            return migrated

        except Exception as error:
            print(f"[Health Monitor] Failed to load alert state: {error}")

            return {}

    @staticmethod
    def _is_obsolete_download_alert(alert: dict) -> bool:
        return alert.get("monitor_source") == "downloads" or alert.get(
            "issue_type"
        ) in {"download", "stalled_download"}

    def _monitor_source_from_issue_type(
        self,
        issue_type: str,
    ) -> str:
        if issue_type == "unknown":
            return "unknown"

        if issue_type == "pipeline":
            return self.PIPELINE_MONITOR_SOURCE

        if issue_type == "storage":
            return self.STORAGE_MONITOR_SOURCE

        return self.SABNZBD_MONITOR_SOURCE

    def _check_storage(self) -> tuple[list[HealthIssue], bool]:
        media_root = Config.MEDIA_ROOT

        if not media_root:
            print(
                "[Health Monitor] Storage check failed: MEDIA_ROOT is not configured."
            )
            return [], False

        monitored_path = Path(media_root)

        if not monitored_path.is_dir():
            print(
                "[Health Monitor] Storage check failed: "
                f"MEDIA_ROOT is not an existing directory: {monitored_path}"
            )
            return [], False

        try:
            total, _, available = shutil.disk_usage(monitored_path)
        except OSError as error:
            print(f"[Health Monitor] Storage check failed: {error}")
            return [], False

        available_percentage = (available / total) * 100 if total else 0
        severity = None

        if available_percentage < Config.STORAGE_CRITICAL_THRESHOLD_PERCENT:
            severity = "critical"
        elif available_percentage < Config.STORAGE_WARNING_THRESHOLD_PERCENT:
            severity = "warning"

        if severity is None:
            return [], True

        return [
            HealthIssue(
                title="NAS Storage Low",
                issue_type="storage",
                details=(
                    f"Monitored Path: {monitored_path}\n"
                    f"Total Capacity: {format_size(total)}\n"
                    f"Available Capacity: {format_size(available)}\n"
                    f"Available Percentage: {available_percentage:.1f}%"
                ),
                created_at=datetime.now(),
                severity=severity,
            )
        ], True

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

    def _check_sab_queue(self) -> tuple[list[HealthIssue], bool]:
        issues: list[HealthIssue] = []

        try:
            queue = self.sabnzbd.get_queue()

        except Exception as error:
            return [self._sab_queue_failure_issue(error)], False

        try:
            slots = queue["queue"]["slots"]
        except (KeyError, TypeError) as error:
            return [self._sab_queue_failure_issue(error)], False

        if not isinstance(slots, list):
            return [self._sab_queue_failure_issue("invalid queue slots")], False

        logger.debug("[Health Monitor] SAB queue items: %s", len(slots))

        return issues, True

    def _sab_queue_failure_issue(self, error: Exception | str) -> HealthIssue:
        return HealthIssue(
            title="SABnzbd Offline",
            issue_type="service",
            details=("Unable to retrieve the SABnzbd queue.\n" f"Error: {error}"),
            created_at=datetime.now(),
            severity="critical",
            monitor_source=self.SABNZBD_MONITOR_SOURCE,
        )
