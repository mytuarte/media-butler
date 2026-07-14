import json

from config import Config
from models.overseerr_request import OverseerrRequest
from services.http_service import HttpService
from services.overseerr_request_factory import (
    OverseerrRequestFactory,
)


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

    def get_request_lookup(
        self,
    ) -> dict[int, OverseerrRequest]:
        requests = self.get_requests()

        lookup = {}

        for request in requests["results"]:
            media = request.get("media", {})
            tmdb_id = media.get("tmdbId")

            if tmdb_id is None:
                continue

            lookup[tmdb_id] = OverseerrRequestFactory.from_api(request)

        return lookup

    def get_request(self, tmdb_id: int) -> OverseerrRequest | None:
        lookup = self.get_request_lookup()

        return lookup.get(tmdb_id)

    def delete_request(self, request_id: int):
        return self.http.delete(
            f"{Config.OVERSEERR_URL}/api/v1/request/{request_id}",
            headers=self.headers,
        )

    def debug_request(self, tmdb_id):
        request = self.get_request(tmdb_id)

        if request is None:
            print(f"No Overseerr request found for TMDb ID {tmdb_id}")
            return None

        print("\n" + "=" * 70)
        print(f"TMDb ID: {tmdb_id}")
        print("=" * 70)
        print(json.dumps(request.raw, indent=4))
        print("=" * 70 + "\n")

        return request
