"""Persistent deduplication state for TV completion notifications."""
import json
from pathlib import Path

from services.log_service import logger


class SeriesCompletionNotificationStateStore:
    VERSION = 1

    def __init__(self, state_file: Path = Path("data/series_completion_notifications.json")):
        self.state_file = state_file

    def load(self) -> dict[str, dict]:
        try:
            contents = self.state_file.read_text()
        except FileNotFoundError:
            return {}
        except OSError as error:
            logger.warning("[Series Completion] Failed to load state: %s", error)
            return {}
        if not contents.strip():
            return {}
        try:
            data = json.loads(contents)
            if data.get("version") != self.VERSION or not isinstance(data.get("series"), dict):
                raise ValueError("Unsupported series completion state.")
            return data["series"]
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            logger.warning("[Series Completion] Failed to load state: %s", error)
            return {}

    def save(self, series: dict[str, dict]) -> None:
        temporary_file = self.state_file.with_suffix(".tmp")
        data = {"version": self.VERSION, "series": series}
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary_file.write_text(json.dumps(data, indent=4, sort_keys=True))
            temporary_file.replace(self.state_file)
        except OSError as error:
            logger.warning("[Series Completion] Failed to save state: %s", error)
            raise
