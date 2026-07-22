import requests

from config import Config
from services.log_service import logger


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
        logger.info("Plex availability check: tmdb_id=%s", tmdb_id)
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
        logger.info("Plex search results for tmdb_id=%s: %s", tmdb_id, metadata)
        expected_guid = f"tmdb://{tmdb_id}"
        for item in metadata:
            external_ids = [guid.get("id") for guid in item.get("Guid", [])]
            logger.info(
                "Plex external IDs for tmdb_id=%s: %s", tmdb_id, external_ids
            )
            if expected_guid in external_ids:
                logger.info("Plex availability match found: tmdb_id=%s", tmdb_id)
                return True

        logger.info(
            "Plex unavailable: no result contained TMDb GUID %s", expected_guid
        )
        return False
