"""HTTP client for Kling AI Motion Control API."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

BASE_URL = "https://api-singapore.klingai.com"


class KlingAPIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class AuthError(KlingAPIError):
    pass


class RateLimitError(KlingAPIError):
    pass


class InsufficientCreditsError(KlingAPIError):
    pass


class KlingClient:
    """Thin synchronous wrapper around Kling Motion Control endpoints."""

    def __init__(self, token: str, base_url: str = BASE_URL, timeout: float = 60.0):
        self._client = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=timeout,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- Motion Control ---

    def create_motion_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/v1/videos/motion-control", json=payload)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v1/videos/motion-control/{task_id}")

    def list_tasks(self, page: int = 1, page_size: int = 30) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/v1/videos/motion-control",
            params={"pageNum": page, "pageSize": page_size},
        )

    # --- internals ---

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code in (401, 403):
            raise AuthError(resp.status_code, resp.text)
        if resp.status_code == 429:
            raise RateLimitError(resp.status_code, resp.text)
        if resp.status_code == 402:
            raise InsufficientCreditsError(resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()
