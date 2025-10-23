"""HTTP proxy utilities for forwarding requests to GURS services."""

from __future__ import annotations

import asyncio
import time
from typing import Final
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.requests import Request
from starlette.responses import Response

from .config import INSPIRE_WMS_DTM_URL, WFS_URL

_ALLOWED_BASE_URLS: Final[tuple[str, ...]] = (WFS_URL, INSPIRE_WMS_DTM_URL)
_DEFAULT_TIMEOUT = httpx.Timeout(20.0)

router = APIRouter(prefix="/gurs", tags=["GURS Proxy"])


class TokenBucket:
    """A cooperative asynchronous token bucket."""

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self, amount: float = 1.0) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.updated_at
            if elapsed > 0:
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
                self.updated_at = now
            if self.tokens < amount:
                return False
            self.tokens -= amount
            return True


def _validate_target_url(raw_url: str) -> str:
    if not raw_url:
        raise HTTPException(status_code=400, detail="Parameter 'url' is required")

    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="A valid absolute URL is required")

    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if not any(normalized.startswith(base) for base in _ALLOWED_BASE_URLS):
        raise HTTPException(status_code=400, detail="URL ni dovoljen za proxy posredovanje")

    return raw_url


_token_bucket = TokenBucket(capacity=40, refill_rate=2.0)


async def _rate_limit() -> None:
    allowed = await _token_bucket.consume()
    if not allowed:
        raise HTTPException(status_code=429, detail="Preveč zahtevkov na GURS proxy")


@router.get("/proxy")
async def proxy_request(
    request: Request,
    url: str = Query(..., description="Ciljni URL za posredovanje"),
    _: None = Depends(_rate_limit),
) -> Response:
    """Forward GET requests to approved GURS endpoints."""

    target_url = _validate_target_url(url)

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            upstream_response = await client.get(target_url, headers={"Accept": request.headers.get("accept", "*/*")})
    except httpx.HTTPError as exc:  # pragma: no cover - defensive mapping
        raise HTTPException(status_code=502, detail=f"Napaka pri posredovanju: {exc}") from exc

    content_type = upstream_response.headers.get("content-type")
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=content_type,
        headers={
            k: v
            for k, v in upstream_response.headers.items()
            if k.lower().startswith("cache-")
        },
    )
