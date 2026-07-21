from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState
from services.discovery.tmdb_service import TmdbService
from services.overseerr_service import OverseerrService
from services.radarr_service import RadarrService
from services.sonarr_service import SonarrService


class DiscoveryService:
    TRENDING_MOVIE_CANDIDATE_PAGES = 5

    def __init__(self):
        self.tmdb = TmdbService()
        self.radarr = RadarrService()
        self.sonarr = SonarrService()
        self.overseerr = OverseerrService()

    def get_trending_movies(self) -> list[DiscoveryItem]:
        items = self.tmdb.get_trending_movies()

        self._enrich(items)

        return items

    def get_watchable_trending_movies(self) -> tuple[list[DiscoveryItem], int]:
        """Get enough ranked candidates to fill the digital-only dashboard.

        Provider filtering is deliberately performed before local-state
        enrichment: Plex, Radarr, and Overseerr only determine the status icon
        after TMDB has established that the movie is watchable digitally.
        """
        candidates = self.tmdb.get_trending_movies(
            pages=self.TRENDING_MOVIE_CANDIDATE_PAGES
        )
        watchable = [
            movie
            for movie in candidates
            if self.tmdb.movie_has_digital_availability(movie.tmdb_id)
        ]
        self._enrich(watchable)
        return watchable, len(candidates)

    def get_trending_tv(self) -> list[DiscoveryItem]:
        items = self.tmdb.get_trending_tv()

        self._enrich(items)

        return items

    def get_digital_movies(self) -> list[DiscoveryItem]:
        items = self.tmdb.get_digital_movies()

        self._enrich(items)

        return items

    def _enrich(
        self,
        items: list[DiscoveryItem],
    ) -> None:
        self._enrich_monitoring_state(items)
        self._enrich_requests(items)

    def _enrich_monitoring_state(
        self,
        items: list[DiscoveryItem],
    ) -> None:
        movie_states = self.radarr.get_monitoring_states()
        tv_states = self.sonarr.get_monitoring_states()

        for item in items:
            if item.media_type == "movie":
                state, detail = movie_states.get(
                    item.tmdb_id,
                    (
                        MonitoringState.NOT_ADDED,
                        None,
                    ),
                )
            else:
                state, detail = tv_states.get(
                    item.tmdb_id,
                    (
                        MonitoringState.NOT_ADDED,
                        None,
                    ),
                )

            item.monitoring_state = state
            item.status_detail = detail

    def _enrich_requests(
        self,
        items: list[DiscoveryItem],
    ) -> None:
        request_lookup = self.overseerr.get_request_lookup()

        for item in items:
            request = request_lookup.get(item.tmdb_id)

            if request is None:
                continue

            item.requester = request.requester
