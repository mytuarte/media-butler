import requests


class HttpService:
    def get(self, url, headers=None, params=None):
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()