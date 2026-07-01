from config import Config
from services.http_service import HttpService


class OverseerrService:
    def __init__(self):
        self.http = HttpService()

        self.headers = {
            "X-Api-Key": Config.OVERSEERR_API_KEY,
        }

    def test_connection(self):
        return self.http.get(
            f"{Config.OVERSEERR_URL}/api/v1/status",
            headers=self.headers,
        )

    def get_requests(self):
        return self.http.get(
            f"{Config.OVERSEERR_URL}/api/v1/request",
            headers=self.headers,
        )