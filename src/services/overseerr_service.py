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

    def get_requester(self, tmdb_id):
        requests = self.get_requests()

        for request in requests["results"]:
            media = request.get("media", {})

            if media.get("tmdbId") == tmdb_id:
                display_name = request["requestedBy"]["displayName"]

                print(f"Overseerr display name: '{display_name}'")
                print(f"Config.USERS: {Config.USERS}")

                return Config.USERS.get(display_name, display_name)

        print(f"No Overseerr request found for TMDb ID {tmdb_id}")

        return "Unknown"