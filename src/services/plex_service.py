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
        endpoint = f"{Config.PLEX_URL}/library/all"
        query = {
            "type": 1,
            "guid": f"tmdb://{tmdb_id}",
            "includeGuids": 1,
        }
        logger.info(
            "Plex movie lookup request: tmdb_id=%s endpoint=%s query=%s requested_title=%r",
            tmdb_id,
            endpoint,
            query,
            title,
        )
        response = requests.get(
            endpoint,
            params={
                "X-Plex-Token": Config.PLEX_TOKEN,
                **query,
            },
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
        sections = {
            "scope": "all",
            **{
                key: media_container[key]
                for key in (
                    "librarySectionID",
                    "librarySectionTitle",
                    "librarySectionUUID",
                )
                if key in media_container
            },
        }
        logger.info("Plex movie lookup library sections searched: %s", sections)
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

        expected_guid = f"tmdb://{tmdb_id}"
        for item in metadata:
            guids = item.get("Guid", [])
            external_ids = [guid.get("id") for guid in guids]
            item_sections = {
                key: item[key]
                for key in (
                    "librarySectionID",
                    "librarySectionTitle",
                    "librarySectionUUID",
                )
                if key in item
            }
            logger.info(
                "Plex movie lookup result: title=%r year=%r ratingKey=%r "
                "guids=%s external_ids=%s library_sections=%s",
                item.get("title"),
                item.get("year"),
                item.get("ratingKey"),
                guids,
                external_ids,
                item_sections,
            )
            if expected_guid in external_ids:
                logger.info("Plex availability match found: tmdb_id=%s", tmdb_id)
                return True

        logger.info("Plex unavailable: no result contained TMDb GUID %s", expected_guid)
        return False
