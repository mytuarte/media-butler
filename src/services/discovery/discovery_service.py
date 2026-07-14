from services.discovery.tmdb_service import TmdbService


class DiscoveryService:
    def __init__(self):
        self.tmdb = TmdbService()

    def get_trending_movies(self):
        return self.tmdb.get_trending_movies()
