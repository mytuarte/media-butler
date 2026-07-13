from services.radarr_service import RadarrService


class MediaService:
    def __init__(self):
        self.radarr = RadarrService()

    def search(self, query: str):
        return self.radarr.search(query)