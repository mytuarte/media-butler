import requests

from config import Config
from services.log_service import logger


class PlexService:
    MOVIE_TYPE = 1
    CONTAINER_SIZE = 1000

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
        endpoint = f"{Config.PLEX_URL}/library/sections"
        query = {}
        logger.info(
            "Plex movie lookup request: tmdb_id=%s endpoint=%s query=%s requested_title=%r",
            tmdb_id,
            endpoint,
            query,
            title,
        )
        response = requests.get(
            endpoint,
            params={"X-Plex-Token": Config.PLEX_TOKEN},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        logger.info(
            "Plex movie lookup response: endpoint=%s http_status=%s",
            endpoint,
            response.status_code,
        )
        response.raise_for_status()

        expected_guid = f"tmdb://{tmdb_id}"
        sections = response.json().get("MediaContainer", {}).get("Directory", [])
        movie_sections = [
            section for section in sections if section.get("type") == "movie"
        ]
        logger.info(
            "Plex movie lookup library sections searched: %s",
            [
                {
                    key: section[key]
                    for key in ("key", "title", "uuid")
                    if key in section
                }
                for section in movie_sections
            ],
        )

        for section in movie_sections:
            if self._section_has_tmdb_guid(section, expected_guid):
                logger.info("Plex availability match found: tmdb_id=%s", tmdb_id)
                return True

        self._log_title_fallback_diagnostics(f"{Config.PLEX_URL}/library/all", title)
        logger.info("Plex unavailable: no result contained TMDb GUID %s", expected_guid)
        return False

    def _section_has_tmdb_guid(self, section: dict, expected_guid: str) -> bool:
        """Inspect every movie in a section because Plex cannot filter on Guid ids.

        Plex's ``guid`` query filter addresses an item's primary Plex GUID, while
        TMDb identities are returned in the nested ``Guid`` list. Fetching movie
        section contents with ``includeGuids`` and checking that list preserves
        the required exact external identity match.
        """
        endpoint = f"{Config.PLEX_URL}/library/sections/{section['key']}/all"
        start = 0
        while True:
            query = {
                "type": self.MOVIE_TYPE,
                "includeGuids": 1,
                "X-Plex-Container-Start": start,
                "X-Plex-Container-Size": self.CONTAINER_SIZE,
            }
            logger.info(
                "Plex movie lookup request: endpoint=%s query=%s", endpoint, query
            )
            response = requests.get(
                endpoint,
                params={"X-Plex-Token": Config.PLEX_TOKEN, **query},
                headers={"Accept": "application/json"},
                timeout=10,
            )
            logger.info(
                "Plex movie lookup response: endpoint=%s http_status=%s",
                endpoint,
                response.status_code,
            )
            response.raise_for_status()

            media_container = response.json().get("MediaContainer", {})
            metadata = media_container.get("Metadata", [])
            logger.info("Plex movie lookup result count: %s", len(metadata))
            if not metadata:
                response_details = {
                    key: value
                    for key, value in media_container.items()
                    if key != "Metadata"
                }
                logger.info(
                    "Plex movie lookup returned zero results: response_details=%s",
                    response_details,
                )

            for item in metadata:
                guids = item.get("Guid", [])
                external_ids = [guid.get("id") for guid in guids]
                logger.info(
                    "Plex movie lookup result: title=%r year=%r ratingKey=%r "
                    "guids=%s external_ids=%s library_sections=%s",
                    item.get("title"),
                    item.get("year"),
                    item.get("ratingKey"),
                    guids,
                    external_ids,
                    {
                        key: item[key]
                        for key in (
                            "librarySectionID",
                            "librarySectionTitle",
                            "librarySectionUUID",
                        )
                        if key in item
                    },
                )
                if expected_guid in external_ids:
                    return True

            total_size = media_container.get("totalSize")
            start += len(metadata)
            if not metadata or total_size is None or start >= total_size:
                return False

    def _log_title_fallback_diagnostics(self, endpoint: str, title: str) -> None:
        """Log title-search candidates after an empty TMDb GUID lookup.

        This diagnostic lookup never contributes to the availability result.
        """
        query = {"type": 1, "title": title, "includeGuids": 1}
        logger.info(
            "Plex title fallback diagnostic request: endpoint=%s query=%s",
            endpoint,
            query,
        )
        try:
            response = requests.get(
                endpoint,
                params={"X-Plex-Token": Config.PLEX_TOKEN, **query},
                headers={"Accept": "application/json"},
                timeout=10,
            )
            logger.info(
                "Plex title fallback diagnostic response: endpoint=%s http_status=%s",
                endpoint,
                response.status_code,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            logger.warning("Plex title fallback diagnostic failed: %s", error)
            return

        metadata = response.json().get("MediaContainer", {}).get("Metadata", [])
        logger.info("Plex title fallback diagnostic result count: %s", len(metadata))
        for item in metadata:
            guids = item.get("Guid", [])
            external_ids = [guid.get("id") for guid in guids]
            logger.info(
                "Plex title fallback diagnostic result: title=%r year=%r ratingKey=%r "
                "guids=%s external_ids=%s",
                item.get("title"),
                item.get("year"),
                item.get("ratingKey"),
                guids,
                external_ids,
            )
