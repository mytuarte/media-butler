import json
from pathlib import Path

from models.media_attention import TrackedMedia


class MediaAttentionStateStore:
    VERSION = 1

    def __init__(self, state_file: Path = Path("data/media_attention.json")):
        self.state_file = state_file

    def load(self) -> dict[str, TrackedMedia]:
        if not self.state_file.exists():
            return {}

        try:
            data = json.loads(self.state_file.read_text())
            if data.get("version") != self.VERSION:
                raise ValueError("Unsupported Media Attention state version.")

            return {
                media_key: TrackedMedia.from_dict(media_key, tracked_media)
                for media_key, tracked_media in data.get("tracked_media", {}).items()
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            print(f"[Media Attention] Failed to load state: {error}")
            return {}

    def save(self, tracked_media: dict[str, TrackedMedia]) -> None:
        data = {
            "version": self.VERSION,
            "tracked_media": {
                media_key: item.to_dict()
                for media_key, item in tracked_media.items()
            },
        }
        temporary_file = self.state_file.with_suffix(".tmp")

        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary_file.write_text(json.dumps(data, indent=4, sort_keys=True))
            temporary_file.replace(self.state_file)
        except OSError as error:
            print(f"[Media Attention] Failed to save state: {error}")
