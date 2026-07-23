import re

import requests

from config import Config


class QbittorrentClient:
    """Probe qBittorrent WebUI availability with an authenticated session."""

    VERSION_PATTERN = re.compile(
        r"^v?\d+(?:\.\d+){1,3}(?:[A-Za-z][A-Za-z0-9._+~:-]*|[-+~][A-Za-z0-9._+~:-]+)?$"
    )

    def __init__(self):
        if not Config.qbittorrent_monitoring_enabled():
            raise ValueError("qBittorrent monitoring is not configured.")

        self.base_url = Config.QBITTORRENT_URL.rstrip("/")
        self.session = requests.Session()
        self.headers = {"Referer": self.base_url}

    def test_connection(self) -> str:
        login_response = self.session.post(
            f"{self.base_url}/api/v2/auth/login",
            data={
                "username": Config.QBITTORRENT_USERNAME,
                "password": Config.QBITTORRENT_PASSWORD,
            },
            headers=self.headers,
            timeout=10,
        )
        login_response.raise_for_status()

        login_result = login_response.text.strip()
        if login_result == "Fails.":
            raise PermissionError("qBittorrent rejected the configured credentials.")
        if login_result != "Ok.":
            raise ValueError("qBittorrent returned an unexpected login response.")

        version_response = self.session.get(
            f"{self.base_url}/api/v2/app/version",
            headers=self.headers,
            timeout=10,
        )
        version_response.raise_for_status()

        version_text = version_response.text
        version = version_text.strip()
        if (
            not version
            or "\n" in version_text
            or "\r" in version_text
            or not self.VERSION_PATTERN.fullmatch(version)
        ):
            raise ValueError("qBittorrent returned an unusable version response.")

        return version
