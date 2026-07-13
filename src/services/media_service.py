from services.overseerr_service import OverseerrService
from services.search.radarr_search_service import RadarrSearchService
from services.search.sonarr_search_service import SonarrSearchService


class MediaService:
    def __init__(self):
        self.search_services = [
            RadarrSearchService(),
            SonarrSearchService(),
        ]

        self.overseerr = OverseerrService()

    def search(self, query: str):
        results = []

        for service in self.search_services:
            results.extend(service.search(query))

        for result in results:
            if result.tmdb_id is None:
                continue

            result.overseerr = self.overseerr.get_request(
                result.tmdb_id
            )

        return results