from services.overseerr_service import OverseerrService
from services.sabnzbd_client import SabnzbdClient
from services.search.radarr_search_service import RadarrSearchService
from services.search.sonarr_search_service import SonarrSearchService


class MediaService:
    def __init__(self):
        self.search_services = [
            RadarrSearchService(),
            SonarrSearchService(),
        ]

        self.overseerr = OverseerrService()
        self.download_client = SabnzbdClient()

    def search(self, query: str):
        results = []

        for service in self.search_services:
            results.extend(service.search(query))

        results.sort(
            key=lambda result: (
                result.year or 0,
                result.title.lower(),
            ),
            reverse=True,
        )

        queue = self.download_client.get_queue()

        for result in results:
            if result.tmdb_id is not None:
                result.overseerr = self.overseerr.get_request(
                    result.tmdb_id
                )

            result.download = self.download_client.get_download(
                result,
                queue,
            )

        return results