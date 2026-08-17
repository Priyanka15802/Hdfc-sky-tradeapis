from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter, Retry

from .exceptions import APIError


class HttpClient:
    """Thin wrapper around requests.Session shared by AuthClient and
    OrderClient: base URL joining, timeouts, retries on transient network
    errors, bearer-token injection, and uniform error handling.
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.access_token: str | None = None

        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(502, 503, 504),
            allowed_methods=("GET", "POST", "PUT", "DELETE"),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def set_access_token(self, access_token: str | None) -> None:
        self.access_token = access_token

    def request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {}) or {}
        if self.access_token:
            headers.setdefault("Authorization", f"Bearer {self.access_token}")

        response = self.session.request(
            method=method,
            url=url,
            headers=headers,
            timeout=self.timeout,
            **kwargs,
        )

        try:
            payload = response.json() if response.content else {}
        except ValueError:
            payload = {"raw": response.text}

        if not response.ok:
            raise APIError(response.status_code, payload)

        return payload
