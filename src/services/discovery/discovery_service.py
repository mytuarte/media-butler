from models.discovery.discovery_item import DiscoveryItem
from services.discovery.tmdb_service import TmdbService
from services.overseerr_service import OverseerrService
from services.radarr_service import RadarrService
from services.sonarr_service import SonarrService


class DiscoveryService:
    def __init__(self):
        self.tmdb = TmdbService()
        self.radarr = RadarrService()
        self.sonarr = SonarrService()
        self.overseerr = OverseerrService()

    def get_trending_movies(self) -> list[DiscoveryItem]:
        items = self.tmdb.get_trending_movies()

        self._enrich(items)

        return items

    def get_trending_tv(self) -> list[DiscoveryItem]:
        items = self.tmdb.get_trending_tv()

        self._enrich(items)

        return items

    def get_digital_movies(self) -> list[DiscoveryItem]:
        items = self.tmdb.get_digital_movies()

        self._enrich(items)

        return items

    def _enrich(self, items: list[DiscoveryItem]) -> None:
        self._enrich_library(items)
        self._enrich_requests(items)

    def _enrich_library(
        self,
        items: list[DiscoveryItem],
    ) -> None:
        movie_tmdb_ids = self.radarr.get_tmdb_ids()
        tv_tmdb_ids = self.sonarr.get_tmdb_ids()

        for item in items:
            if item.media_type == "movie":
                item.in_library = item.tmdb_id in movie_tmdb_ids

            elif item.media_type == "tv":
                item.in_library = item.tmdb_id in tv_tmdb_ids

    def _enrich_requests(
        self,
        items: list[DiscoveryItem],
    ) -> None:
        request_lookup = self.overseerr.get_request_lookup()

        for item in items:
            request = request_lookup.get(item.tmdb_id)

            if request is None:
                continue

            item.requested = True
            item.requester = request.requester
