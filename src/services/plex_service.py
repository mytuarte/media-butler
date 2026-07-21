import requests

from config import Config


class PlexService:
    def test_connection(self):
        response = requests.get(
            f"{Config.PLEX_URL}/identity",
            params={
                "X-Plex-Token": Config.PLEX_TOKEN,
            },
            timeout=10,
        )

        response.raise_for_status()
