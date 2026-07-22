import time

import requests

from config import Config
from services.log_service import logger


class PlexService:
    MOVIE_TYPE = 1
    CONTAINER_SIZE = 1000

    def __init__(self):
        self._movie_inventory: dict[int, dict] = {}
        self._movie_inventory_refreshed_at: float | None = None

    def test_connection(self):
        response = requests.get(
            f"{Config.PLEX_URL}/identity",
            params={"X-Plex-Token": Config.PLEX_TOKEN},
            timeout=10,
        )
        response.raise_for_status()

    def movie_is_available(self, tmdb_id: int, title: str) -> bool:
        """Return whether Plex has a movie with the exact requested TMDb GUID."""
        del title
        inventory = self._movie_inventory_for_lookup()
        available = tmdb_id in inventory
        logger.info(
            "Plex availability %s: tmdb_id=%s",
            "match found" if available else "not found",
            tmdb_id,
        )
        return available

    def _movie_inventory_for_lookup(self) -> dict[int, dict]:
        if self._inventory_needs_refresh():
            self._refresh_movie_inventory()
        return self._movie_inventory

    def _inventory_needs_refresh(self) -> bool:
        if not self._movie_inventory or self._movie_inventory_refreshed_at is None:
            return True
        return (
            time.monotonic() - self._movie_inventory_refreshed_at
            >= Config.PLEX_INVENTORY_CACHE_SECONDS
        )

    def _refresh_movie_inventory(self) -> None:
        """Fetch and atomically replace the complete Plex movie inventory.

        The instance cache is changed only after every section and page has been
        fetched successfully, so a failed refresh leaves known-good data intact.
        """
        logger.info("Plex movie inventory refresh started")
        endpoint = f"{Config.PLEX_URL}/library/sections"
        try:
            response = requests.get(
                endpoint,
                params={"X-Plex-Token": Config.PLEX_TOKEN},
                headers={"Accept": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            sections = response.json().get("MediaContainer", {}).get("Directory", [])
            movie_sections = [
                section for section in sections if section.get("type") == "movie"
            ]

            inventory: dict[int, dict] = {}
            movie_count = 0
            for section in movie_sections:
                for item in self._section_movie_inventory(section):
                    movie_count += 1
                    for tmdb_id in self._tmdb_ids(item):
                        inventory[tmdb_id] = item
        except requests.RequestException as error:
            logger.warning("Plex movie inventory refresh failed: %s", error)
            raise

        self._movie_inventory = inventory
        self._movie_inventory_refreshed_at = time.monotonic()
        logger.info(
            "Plex movie inventory refresh completed: movie_sections=%s movies_indexed=%s",
            len(movie_sections),
            movie_count,
        )

    def _section_movie_inventory(self, section: dict):
        endpoint = f"{Config.PLEX_URL}/library/sections/{section['key']}/all"
        start = 0
        while True:
            response = requests.get(
                endpoint,
                params={
                    "X-Plex-Token": Config.PLEX_TOKEN,
                    "type": self.MOVIE_TYPE,
                    "includeGuids": 1,
                    "X-Plex-Container-Start": start,
                    "X-Plex-Container-Size": self.CONTAINER_SIZE,
                },
                headers={"Accept": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            media_container = response.json().get("MediaContainer", {})
            metadata = media_container.get("Metadata", [])
            yield from metadata

            start += len(metadata)
            total_size = media_container.get("totalSize")
            if not metadata or total_size is None or start >= total_size:
                return

    @staticmethod
    def _tmdb_ids(item: dict) -> list[int]:
        """Extract TMDb IDs solely from exact ``tmdb://<integer>`` GUIDs."""
        tmdb_ids = []
        for guid in item.get("Guid", []):
            value = guid.get("id", "")
            if value.startswith("tmdb://"):
                try:
                    tmdb_id = int(value.removeprefix("tmdb://"))
                except ValueError:
                    continue
                if value == f"tmdb://{tmdb_id}":
                    tmdb_ids.append(tmdb_id)
        return tmdb_ids
