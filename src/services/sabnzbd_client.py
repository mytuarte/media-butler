import requests

from config import Config
from models.download_status import DownloadStatus


class SabnzbdClient:
    """
    Retrieves information from SABnzbd.
    """

    def test_connection(self) -> dict:
        response = requests.get(
            f"{Config.SABNZBD_URL}/api",
            params={
                "mode": "version",
                "apikey": Config.SABNZBD_API_KEY,
                "output": "json",
            },
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def get_queue(self) -> dict:
        response = requests.get(
            f"{Config.SABNZBD_URL}/api",
            params={
                "mode": "queue",
                "apikey": Config.SABNZBD_API_KEY,
                "output": "json",
            },
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def _normalize(text: str) -> str:
        return text.lower().replace(".", " ").replace("_", " ").replace("-", " ")

    def get_download(
        self,
        media_result,
        queue: dict | None = None,
    ) -> DownloadStatus | None:
        if queue is None:
            queue = self.get_queue()

        slots = queue.get("queue", {}).get("slots", [])

        title = self._normalize(media_result.title)

        for slot in slots:
            filename = self._normalize(slot.get("filename", ""))

            if title not in filename:
                continue

            return DownloadStatus(
                name=slot.get(
                    "filename",
                    "Unknown Download",
                ),
                state=slot.get(
                    "status",
                    "Unknown",
                ),
                progress=int(
                    slot.get(
                        "percentage",
                        0,
                    )
                ),
                eta=slot.get(
                    "timeleft",
                    "Unknown",
                ),
            )

        return None
