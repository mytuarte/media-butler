from config import Config
from services.http_service import HttpService


class OverseerrService:
    def __init__(self):
        self.http = HttpService()

    def test_connection(self):
        return self.http.get(
            f"{Config.OVERSEERR_URL}/api/v1/status",
            headers={
                "X-Api-Key": Config.OVERSEERR_API_KEY,
            },
        )