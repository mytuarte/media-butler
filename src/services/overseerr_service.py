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

        self._request_lookup: dict[int, OverseerrRequest] | None = None

    def test_connection(self):
        return self.http.get(
            f"{Config.OVERSEERR_URL}/api/v1/auth/me",
            headers=self.headers,
        )

    def get_requests(self):
        page = 1
        results = []

        while True:
            response = self.http.get(
                f"{Config.OVERSEERR_URL}/api/v1/request",
                headers=self.headers,
                params={
                    "take": 100,
                    "skip": (page - 1) * 100,
                },
            )

            results.extend(response["results"])

            page_info = response["pageInfo"]

            if page >= page_info["pages"]:
                break

            page += 1

        return {
            "results": results,
        }

    def get_request_lookup(
        self,
        refresh: bool = False,
    ) -> dict[int, OverseerrRequest]:
        if self._request_lookup is not None and not refresh:
            return self._request_lookup

        requests = self.get_requests()

        lookup = {}

        for request in requests["results"]:
            media = request.get("media", {})
            tmdb_id = media.get("tmdbId")

            if tmdb_id is None:
                continue

            lookup[tmdb_id] = OverseerrRequestFactory.from_api(request)

        self._request_lookup = lookup

        return lookup

    def get_request(
        self,
        tmdb_id: int,
        refresh: bool = False,
    ) -> OverseerrRequest | None:
        lookup = self.get_request_lookup(refresh=refresh)

        return lookup.get(tmdb_id)

    def invalidate_request_cache(self):
        self._request_lookup = None

    def delete_request(self, request_id: int):
        response = self.http.delete(
            f"{Config.OVERSEERR_URL}/api/v1/request/{request_id}",
            headers=self.headers,
        )
        self.invalidate_request_cache()

        return response

    def clear_media_data(self, media_id: int):
        response = self.http.delete(
            f"{Config.OVERSEERR_URL}/api/v1/media/{media_id}",
            headers=self.headers,
        )
        self.invalidate_request_cache()

        return response

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
