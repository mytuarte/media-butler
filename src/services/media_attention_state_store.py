import json
import os
import tempfile
import threading
import time
from pathlib import Path

from models.media_attention import TrackedMedia
from services.log_service import logger


class MediaAttentionStateStore:
    VERSION = 1
    REPLACE_RETRIES = 3
    REPLACE_RETRY_DELAY_SECONDS = 0.05

    def __init__(self, state_file: Path = Path("data/media_attention.json")):
        self.state_file = state_file
        self._save_lock = threading.Lock()

    def load(self) -> dict[str, TrackedMedia]:
        try:
            contents = self.state_file.read_text()
        except FileNotFoundError:
            return {}
        except OSError as error:
            logger.warning("[Media Attention] Failed to load state: %s", error)
            return {}

        if not contents.strip():
            return {}

        try:
            data = json.loads(contents)
            if data.get("version") != self.VERSION:
                raise ValueError("Unsupported Media Attention state version.")

            return {
                media_key: TrackedMedia.from_dict(media_key, tracked_media)
                for media_key, tracked_media in data.get("tracked_media", {}).items()
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            logger.warning("[Media Attention] Failed to load state: %s", error)
            return {}

    def save(self, tracked_media: dict[str, TrackedMedia]) -> None:
        """Atomically persist a snapshot without risking the previous valid state."""
        with self._save_lock:
            # Materialize before writing so the JSON represents one consistent
            # tracked-state snapshot even when callers later mutate the mapping.
            data = {
                "version": self.VERSION,
                "tracked_media": {
                    media_key: item.to_dict() for media_key, item in tracked_media.items()
                },
            }
            temporary_name = None
            try:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.state_file.parent,
                    prefix=f".{self.state_file.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary_file:
                    temporary_name = temporary_file.name
                    json.dump(data, temporary_file, indent=4, sort_keys=True)
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())

                for attempt in range(self.REPLACE_RETRIES):
                    try:
                        os.replace(temporary_name, self.state_file)
                        temporary_name = None
                        return
                    except PermissionError:
                        if attempt == self.REPLACE_RETRIES - 1:
                            raise
                        time.sleep(self.REPLACE_RETRY_DELAY_SECONDS * (attempt + 1))
            except OSError as error:
                logger.warning("[Media Attention] Failed to save state: %s", error)
            finally:
                if temporary_name is not None:
                    try:
                        os.unlink(temporary_name)
                    except FileNotFoundError:
                        pass
                    except OSError as error:
                        logger.warning(
                            "[Media Attention] Failed to remove temporary state file: %s",
                            error,
                        )
