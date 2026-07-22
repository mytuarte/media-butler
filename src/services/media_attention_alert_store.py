import json
from pathlib import Path

from models.media_attention import MediaAttentionAlert
from services.log_service import logger


class MediaAttentionAlertStore:
    """Persistent active and resolved movie attention alert state."""

    VERSION = 1

    def __init__(self, state_file: Path = Path("data/media_attention_alerts.json")):
        self.state_file = state_file

    def load(self) -> dict[str, MediaAttentionAlert]:
        try:
            contents = self.state_file.read_text()
        except FileNotFoundError:
            return {}
        except OSError as error:
            logger.warning("[Media Attention] Failed to load alert state: %s", error)
            return {}

        if not contents.strip():
            return {}

        try:
            data = json.loads(contents)
            if data.get("version") != self.VERSION:
                raise ValueError("Unsupported Media Attention alert state version.")
            return {
                key: MediaAttentionAlert.from_dict(key, value)
                for key, value in data.get("alerts", {}).items()
            }
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            logger.warning("[Media Attention] Failed to load alert state: %s", error)
            return {}

    def save(self, alerts: dict[str, MediaAttentionAlert]) -> None:
        temporary_file = self.state_file.with_suffix(".tmp")
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary_file.write_text(
                json.dumps(
                    {
                        "version": self.VERSION,
                        "alerts": {
                            key: alert.to_dict() for key, alert in alerts.items()
                        },
                    },
                    indent=4,
                    sort_keys=True,
                )
            )
            temporary_file.replace(self.state_file)
        except OSError as error:
            print(f"[Media Attention] Failed to save alert state: {error}")
