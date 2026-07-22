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

    def movie_is_available(self, tmdb_id: int, title: str) -> bool:
        """Return whether Plex has a movie with the requested TMDb identity.

        The TMDb guid is authoritative so a same-title movie cannot be treated
        as available by mistake.
        """
        response = requests.get(
            f"{Config.PLEX_URL}/library/all",
            params={
                "X-Plex-Token": Config.PLEX_TOKEN,
                "type": 1,
                "guid": f"tmdb://{tmdb_id}",
                "includeGuids": 1,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        response.raise_for_status()

        metadata = response.json().get("MediaContainer", {}).get("Metadata", [])
        for item in metadata:
            guids = item.get("Guid", [])
            if any(guid.get("id") == f"tmdb://{tmdb_id}" for guid in guids):
                return True

        return False
