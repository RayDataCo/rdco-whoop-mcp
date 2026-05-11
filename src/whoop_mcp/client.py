"""Whoop API v2 client. Handles auth refresh, rate limiting, and pagination."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

import httpx

from . import auth

logger = logging.getLogger(__name__)

WHOOP_API_BASE = "https://api.prod.whoop.com/developer"
WHOOP_OAUTH_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_OAUTH_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"

# Whoop documents 100 req/min as of API v2.
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW_SECONDS = 60.0

DEFAULT_TIMEOUT = 30.0


class WhoopAuthError(RuntimeError):
    """Raised when credentials are missing or refresh fails."""


class WhoopAPIError(RuntimeError):
    """Raised on non-2xx, non-401 responses from the Whoop API."""


class _TokenBucket:
    """Sliding-window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_requests:
                wait = self.window_seconds - (now - self._timestamps[0])
                if wait > 0:
                    logger.debug("Rate limit hit; sleeping %.2fs", wait)
                    await asyncio.sleep(wait)
            self._timestamps.append(time.monotonic())


class WhoopClient:
    """Thin async client around the Whoop developer API."""

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        self._owns_http = http_client is None
        self._bucket = _TokenBucket(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> "WhoopClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # Auth -------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        creds = auth.get_credentials()
        if not creds:
            raise WhoopAuthError(
                "No Whoop credentials configured. Run `whoop-mcp-setup` first."
            )

        access = creds.get("access_token")
        expires_at = creds.get("expires_at") or 0
        # Refresh 60 seconds before expiry as a safety margin.
        if access and time.time() < (expires_at - 60):
            return access

        return await self._refresh_access_token(creds)

    async def _refresh_access_token(self, creds: dict[str, Any]) -> str:
        client_id = creds.get("client_id")
        client_secret = creds.get("client_secret")
        refresh_token = creds.get("refresh_token")
        if not (client_id and client_secret and refresh_token):
            raise WhoopAuthError(
                "Incomplete credentials. Need client_id, client_secret, refresh_token. "
                "Run `whoop-mcp-setup`."
            )

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "offline",
        }
        resp = await self._http.post(
            WHOOP_OAUTH_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise WhoopAuthError(
                f"Token refresh failed ({resp.status_code}): {resp.text[:300]}"
            )
        body = resp.json()
        new_access = body["access_token"]
        new_refresh = body.get("refresh_token", refresh_token)
        expires_in = body.get("expires_in", 3600)
        expires_at = time.time() + float(expires_in)
        auth.update_tokens(new_access, new_refresh, expires_at)
        return new_access

    # Request plumbing -------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> Any:
        await self._bucket.acquire()
        token = await self._get_access_token()
        url = f"{WHOOP_API_BASE}{path}"
        headers = {"Authorization": f"Bearer {token}"}

        resp = await self._http.request(method, url, params=params, headers=headers)

        if resp.status_code == 401 and retry_on_401:
            # Force a refresh and try once more.
            creds = auth.get_credentials()
            if creds:
                await self._refresh_access_token(creds)
            return await self._request(method, path, params=params, retry_on_401=False)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "5"))
            logger.warning("429 from Whoop API; sleeping %.1fs", retry_after)
            await asyncio.sleep(retry_after)
            return await self._request(method, path, params=params, retry_on_401=False)

        if not (200 <= resp.status_code < 300):
            raise WhoopAPIError(
                f"{method} {path} failed ({resp.status_code}): {resp.text[:300]}"
            )

        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def _paginate(
        self,
        path: str,
        params: dict[str, Any],
        max_pages: int = 50,
    ) -> list[dict[str, Any]]:
        """Walk Whoop's `nextToken` cursor pagination."""
        all_records: list[dict[str, Any]] = []
        page_params = dict(params)
        for _ in range(max_pages):
            body = await self._request("GET", path, params=page_params)
            if body is None:
                break
            records = body.get("records", []) if isinstance(body, dict) else []
            all_records.extend(records)
            next_token = body.get("next_token") if isinstance(body, dict) else None
            if not next_token:
                break
            page_params["nextToken"] = next_token
        return all_records

    # High-level endpoints ---------------------------------------------------

    async def get_profile(self) -> dict[str, Any]:
        """Return the user profile, including basic body measurements."""
        basic = await self._request("GET", "/v2/user/profile/basic")
        try:
            measurements = await self._request("GET", "/v2/user/measurement/body")
        except WhoopAPIError as e:
            logger.debug("body measurements unavailable: %s", e)
            measurements = None
        return {"profile": basic, "measurements": measurements}

    async def get_recovery(self, start: str, end: str) -> list[dict[str, Any]]:
        return await self._paginate(
            "/v2/recovery",
            {"start": start, "end": end, "limit": 25},
        )

    async def get_sleep(self, start: str, end: str) -> list[dict[str, Any]]:
        return await self._paginate(
            "/v2/activity/sleep",
            {"start": start, "end": end, "limit": 25},
        )

    async def get_strain(self, start: str, end: str) -> list[dict[str, Any]]:
        """Strain is exposed as physiological cycles in the Whoop API."""
        return await self._paginate(
            "/v2/cycle",
            {"start": start, "end": end, "limit": 25},
        )

    async def get_workouts(self, start: str, end: str) -> list[dict[str, Any]]:
        return await self._paginate(
            "/v2/activity/workout",
            {"start": start, "end": end, "limit": 25},
        )

    async def get_body_measurements(
        self, start: str, end: str
    ) -> list[dict[str, Any]]:
        """Historical body-composition measurements for the date range.

        Whoop API v2 exposes the latest body measurement record at
        `/v2/user/measurement/body` (no date params on the public spec). We pass
        the date range as a best-effort filter; if the endpoint ignores them and
        returns a single current record, callers still get the latest value.
        """
        body = await self._request(
            "GET",
            "/v2/user/measurement/body",
            params={"start": start, "end": end},
        )
        if body is None:
            return []
        if isinstance(body, dict) and "records" in body:
            return body.get("records") or []
        # Endpoint returns a single object rather than a paginated envelope.
        if isinstance(body, dict):
            return [body]
        if isinstance(body, list):
            return body
        return []
