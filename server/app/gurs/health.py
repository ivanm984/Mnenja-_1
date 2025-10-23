"""Utilities for checking availability of upstream GURS services."""

from __future__ import annotations

import httpx

from .config import INSPIRE_WMS_DTM_URL, WFS_URL

_CAPABILITIES_MAX_LENGTH = 5000
_DEFAULT_TIMEOUT = httpx.Timeout(10.0)


async def _fetch_capabilities(url: str, params: dict[str, str]) -> tuple[int, str]:
    """Fetch a capabilities document and return a status/body tuple.

    The body is truncated to the first 5000 characters to keep responses compact.
    Network errors are mapped to an HTTP 503 status with the error message.
    """

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(url, params=params)
    except httpx.HTTPError as exc:  # pragma: no cover - defensive mapping
        return 503, str(exc)[:_CAPABILITIES_MAX_LENGTH]

    body = response.text[:_CAPABILITIES_MAX_LENGTH]
    return response.status_code, body


async def get_wfs_capabilities_status() -> tuple[int, str]:
    """Retrieve the GetCapabilities status for the WFS endpoint."""

    params = {
        "service": "WFS",
        "request": "GetCapabilities",
        "version": "2.0.0",
    }
    return await _fetch_capabilities(WFS_URL, params)


async def get_wms_capabilities_status() -> tuple[int, str]:
    """Retrieve the GetCapabilities status for the INSPIRE WMS endpoint."""

    params = {
        "service": "WMS",
        "request": "GetCapabilities",
        "version": "1.3.0",
    }
    return await _fetch_capabilities(INSPIRE_WMS_DTM_URL, params)
