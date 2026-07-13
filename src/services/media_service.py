from services.search.radarr_search_service import RadarrSearchService
from services.search.sonarr_search_service import SonarrSearchService


class MediaService:
    def __init__(self):
        self.search_services = [
            RadarrSearchService(),
            SonarrSearchService(),
        ]

    def search(self, query: str):
        results = []

        for service in self.search_services:
            results.extend(service.search(query))

        return results