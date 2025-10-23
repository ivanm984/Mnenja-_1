"""FastAPI routes for interacting with GURS services."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from starlette.responses import JSONResponse, Response

from .config import EPSG_3794, LAYERS, WFS_URL
from .health import get_wfs_capabilities_status, get_wms_capabilities_status

router = APIRouter(prefix="/gurs", tags=["GURS"])


@router.get("/capabilities")
async def get_capabilities() -> dict[str, Any]:
    """Return health information and known layers for GURS services."""

    wfs_status, wfs_body = await get_wfs_capabilities_status()
    wms_status, wms_body = await get_wms_capabilities_status()

    return {
        "wfs_status": wfs_status,
        "wfs_body": wfs_body,
        "wms_status": wms_status,
        "wms_body": wms_body,
        "layers": LAYERS,
    }


def _build_parcel_filter(ko_id: int, st_parcele: str) -> str:
    escaped_parcel = st_parcele.replace("'", "''")
    return f"KO_ID={ko_id} AND ST_PARCELE='{escaped_parcel}'"


@router.get("/parcel/{ko_id}/{st_parcele}")
async def get_parcel(ko_id: int, st_parcele: str) -> Response:
    """Fetch a parcel feature collection for the given KO and parcel number."""

    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "typeNames": LAYERS["PARCELE"],
        "outputFormat": "application/json",
        "srsName": EPSG_3794,
        "CQL_FILTER": _build_parcel_filter(ko_id, st_parcele),
    }

    query = urlencode(params, safe="=:")
    target_url = f"{WFS_URL}?{query}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.get(target_url)
    except httpx.HTTPError as exc:  # pragma: no cover - defensive mapping
        raise HTTPException(status_code=502, detail=f"Povezava do GURS ni uspela: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    content_type = response.headers.get("content-type", "application/json")
    if "json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            # Fall through to return raw text below.
            payload = None
        else:
            return JSONResponse(content=payload, status_code=response.status_code)

    return Response(
        content=response.text,
        media_type=content_type,
        status_code=response.status_code,
    )
