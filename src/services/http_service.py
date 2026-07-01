import requests


class HttpService:
    def request(
        self,
        method,
        url,
        headers=None,
        params=None,
        json=None,
    ):
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def get(
        self,
        url,
        headers=None,
        params=None,
    ):
        return self.request(
            "GET",
            url,
            headers=headers,
            params=params,
        )

    def post(
        self,
        url,
        headers=None,
        json=None,
    ):
        return self.request(
            "POST",
            url,
            headers=headers,
            json=json,
        )