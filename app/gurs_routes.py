# app/gurs_routes.py
# POSODOBLJENA VERZIJA

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from .cache import cache_manager
from .config import (
    DEFAULT_MAP_CENTER,
    DEFAULT_MAP_ZOOM,
    ENABLE_REAL_GURS_API,
    GURS_API_TIMEOUT,
    GURS_RASTER_WMS_URL,
    GURS_WFS_URL,
    GURS_WMS_LAYERS,
    GURS_WMS_URL,
    PROJECT_ROOT,
)
from .database import db_manager
from .schemas import MapStatePayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gurs", tags=["GURS"])

# Pot do HTML datoteke za zemljevid
GURS_MAP_HTML = PROJECT_ROOT / "app" / "gurs_map.html"

# Preprost cache za koordinate, da ne kličemo WFS za vsak klik
PARCEL_COORD_CACHE: Dict[str, List[float]] = {}


@router.get("/map", response_class=HTMLResponse)
async def gurs_map_page():
    """Prikaži GURS zemljevid stran."""
    if not GURS_MAP_HTML.exists():
        raise HTTPException(status_code=404, detail="GURS zemljevid ni na voljo")

    return GURS_MAP_HTML.read_text(encoding="utf-8")


@router.get("/map-config")
async def get_map_config(session_id: Optional[str] = None):
    """Vrne konfiguracijo zemljevida skupaj z morebitno shranjeno lokacijo."""
    saved_state_raw = None
    if session_id:
        saved_state_raw = await db_manager.fetch_map_state(session_id)

    saved_state = None
    if saved_state_raw:
        saved_state = {
            "center": [saved_state_raw["center_lon"], saved_state_raw["center_lat"]],
            "zoom": saved_state_raw["zoom"],
            "updated_at": saved_state_raw["updated_at"],
        }

    base_layers = [
        _build_layer_payload(layer_id, layer_cfg)
        for layer_id, layer_cfg in GURS_WMS_LAYERS.items()
        if layer_cfg.get("category") == "base"
    ]
    overlay_layers = [
        _build_layer_payload(layer_id, layer_cfg)
        for layer_id, layer_cfg in GURS_WMS_LAYERS.items()
        if layer_cfg.get("category") == "overlay"
    ]

    return {
        "success": True,
        "config": {
            "default_center": list(DEFAULT_MAP_CENTER),
            "default_zoom": DEFAULT_MAP_ZOOM,
            "wms_url": GURS_WMS_URL,
            "raster_wms_url": GURS_RASTER_WMS_URL,
            "base_layers": base_layers,
            "overlay_layers": overlay_layers,
            "saved_state": saved_state,
        },
    }


@router.get("/map-state/{session_id}")
async def get_map_state(session_id: str):
    """Pridobi shranjeno stanje zemljevida."""
    state = await db_manager.fetch_map_state(session_id)
    if not state:
        return {
            "success": True,
            "state": None,
            "default_center": list(DEFAULT_MAP_CENTER),
            "default_zoom": DEFAULT_MAP_ZOOM,
        }

    return {
        "success": True,
        "state": {
            "center": [state["center_lon"], state["center_lat"]],
            "zoom": state["zoom"],
            "updated_at": state["updated_at"],
        },
    }


@router.post("/map-state/{session_id}")
async def save_map_state(session_id: str, payload: MapStatePayload):
    """Shrani trenutno lokacijo zemljevida za izbrano sejo."""
    session_id_clean = session_id.strip()
    if not session_id_clean:
        raise HTTPException(status_code=400, detail="Manjka session_id")

    await db_manager.save_map_state(
        session_id_clean,
        center_lon=payload.center_lon,
        center_lat=payload.center_lat,
        zoom=payload.zoom,
    )

    cache_key = _parcel_cache_key("__map__", session_id_clean)
    PARCEL_COORD_CACHE[cache_key] = [payload.center_lon, payload.center_lat]

    return {"success": True}


@router.get("/search-parcel")
async def search_parcel(query: str = Query(..., description="Parcela številka (npr. 123/5)")):
    """Išči parcelo po številki."""
    logger.info(f"[GURS] Iskanje parcele: {query}")

    query_clean = query.strip()
    parcel_no, ko_hint = _parse_query_for_parcel(query_clean)

    parcels: List[Dict[str, Any]] = []
    if ENABLE_REAL_GURS_API:
        parcels = await _search_parcel_via_wfs(parcel_no, ko_hint)

    if not parcels:
        logger.debug("[GURS] WFS ni vrnil rezultatov, uporabljam simulacijo")
        mock_parcel = {
            "stevilka": parcel_no,
            "katastrska_obcina": ko_hint or "Litija",
            "coordinates": get_mock_coordinates(parcel_no),
            "povrsina": abs(hash(parcel_no) % 2000) + 500,
            "namenska_raba": "SSe - Površine podeželskega naselja",
        }
        parcels = [mock_parcel]

    return {
        "success": True,
        "parcels": parcels,
    }


@router.get("/session-parcels/{session_id}")
async def get_session_parcels(session_id: str):
    """Pridobi parcele iz AI ekstrakcije za določeno sejo."""
    logger.info(f"[GURS] Pridobivam parcele za sejo: {session_id}")

    data = await cache_manager.retrieve_session_data(session_id)

    if not data:
        raise HTTPException(status_code=404, detail="Seja ne obstaja ali je potekla")

    parcels = extract_parcels_from_session(data)

    logger.info(f"[GURS] Ekstrahiranih {len(parcels)} parcel")

    if not parcels:
        return {
            "success": True,
            "parcels": [],
            "message": "Ni najdenih parcel v projektu",
        }

    parcels_with_coords = []
    for parcel in parcels:
        coords = await _resolve_parcel_coordinates(parcel["stevilka"], parcel.get("katastrska_obcina"))
        parcel["coordinates"] = coords
        parcels_with_coords.append(parcel)
        logger.info(f"[GURS] Parcela {parcel['stevilka']}: {coords}")

    return {
        "success": True,
        "parcels": parcels_with_coords,
    }


def extract_parcels_from_session(session_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Ekstrahiraj podatke o parcelah iz session podatkov."""
    parcels = []

    key_data = session_data.get("key_data", {})

    logger.info(f"[GURS] === EKSTRAHIRAM PARCELE ===")
    logger.info(f"[GURS] Key data keys: {list(key_data.keys())}")

    gradbena_parcela = key_data.get("parcela_objekta", "")
    logger.info(f"[GURS] Gradbena parcela: '{gradbena_parcela}'")

    vse_parcele = key_data.get("stevilke_parcel_ko", "")
    logger.info(f"[GURS] Vse parcele raw: '{vse_parcele}'")

    velikost_str = key_data.get("velikost_parcel", "")
    logger.info(f"[GURS] Velikost: '{velikost_str}'")

    ko_match = re.search(r"k\.o\.\s*(\w+)", vse_parcele, re.IGNORECASE)
    katastrska_obcina = ko_match.group(1) if ko_match else "Litija"
    logger.info(f"[GURS] Katastrska občina: '{katastrska_obcina}'")

    ai_details = session_data.get("ai_details", {})
    namenska_raba_list = ai_details.get("namenska_raba", [])
    namenska_raba = namenska_raba_list[0] if namenska_raba_list else "Ni podatka"
    logger.info(f"[GURS] Namenska raba: '{namenska_raba}'")

    try:
        velikost_match = re.search(r"(\d+[\.,]?\d*)", velikost_str)
        if velikost_match:
            velikost_int = int(float(velikost_match.group(1).replace(',', '.')))
        else:
            velikost_int = 1000
    except (AttributeError, ValueError) as e:
        logger.warning(f"[GURS] Napaka pri parsanju velikosti: {e}")
        velikost_int = 1000

    logger.info(f"[GURS] Parsana velikost: {velikost_int} m²")

    if vse_parcele and vse_parcele.strip():
        parcele_str = re.sub(r"k\.o\..*", "", vse_parcele, flags=re.IGNORECASE)
        logger.info(f"[GURS] Parcele brez K.O.: '{parcele_str}'")

        parcela_numbers = []
        for p in re.split(r'[,;
]', parcele_str):
            p_clean = p.strip()
            if p_clean and p_clean.lower() != 'k.o.' and len(p_clean) > 0:
                parcela_numbers.append(p_clean)

        logger.info(f"[GURS] Najdene parcele: {parcela_numbers}")

        if parcela_numbers:
            povrsina_per_parcel = velikost_int // len(parcela_numbers) if parcela_numbers else velikost_int

            for parcela_num in parcela_numbers:
                parcels.append({
                    "stevilka": parcela_num,
                    "katastrska_obcina": katastrska_obcina,
                    "povrsina": povrsina_per_parcel,
                    "namenska_raba": namenska_raba,
                })

    if not parcels and gradbena_parcela and gradbena_parcela.strip():
        logger.info(f"[GURS] Uporabljam gradbeno parcelo: '{gradbena_parcela}'")
        parcels.append({
            "stevilka": gradbena_parcela.strip(),
            "katastrska_obcina": katastrska_obcina,
            "povrsina": velikost_int,
            "namenska_raba": namenska_raba,
        })

    logger.info(f"[GURS] === REZULTAT: {len(parcels)} parcel ===")
    for i, p in enumerate(parcels, 1):
        logger.info(f"[GURS] Parcela {i}: {p['stevilka']} ({p['katastrska_obcina']})")

    return parcels


def get_mock_coordinates(parcela: str) -> List[float]:
    """Generiraj konsistentne simulirane koordinate za parcelo."""
    base_lon = 14.8267
    base_lat = 46.0569

    hash_val = abs(hash(parcela))

    offset_lon = ((hash_val % 2000) - 1000) * 0.00001
    offset_lat = (((hash_val // 2000) % 2000) - 1000) * 0.00001

    lon = base_lon + offset_lon
    lat = base_lat + offset_lat

    logger.info(f"[GURS] Koordinate za '{parcela}': [{lon:.6f}, {lat:.6f}]")

    return [lon, lat]


@router.get("/parcel-info/{parcela_st}")
async def get_parcel_info(
    parcela_st: str,
    ko: Optional[str] = Query(None, description="Katastrska občina"),
):
    """Pridobi podrobne informacije o parceli."""
    logger.info(f"[GURS] Info za parcelo: {parcela_st}, K.O.: {ko}")

    if ENABLE_REAL_GURS_API:
        parcels = await _search_parcel_via_wfs(parcela_st, ko)
        if parcels:
            return {"success": True, "parcel": parcels[0]}

    return {
        "success": True,
        "parcel": {
            "stevilka": parcela_st,
            "katastrska_obcina": ko or "Litija",
            "povrsina": abs(hash(parcela_st) % 2000) + 500,
            "namenska_raba": "SSe - Površine podeželskega naselja",
            "lastniki": "Zaščiteni podatki",
            "obremenjenja": "Ni",
            "coordinates": get_mock_coordinates(parcela_st),
        },
    }


@router.get("/wms-capabilities")
async def get_wms_capabilities():
    """Vrni informacije o dostopnih GURS WMS slojih."""
    layers: List[Dict[str, Any]] = []
    source = "remote"

    try:
        async with httpx.AsyncClient(timeout=GURS_API_TIMEOUT) as client:
            response = await client.get(
                GURS_WMS_URL,
                params={"service": "WMS", "request": "GetCapabilities"},
            )
            response.raise_for_status()
            layers = _parse_wms_capabilities(response.text)
    except Exception as exc:
        source = "fallback"
        logger.warning(f"[GURS] GetCapabilities ni uspel: {exc}")
        layers = [
            {
                "name": layer_cfg["name"],
                "title": layer_cfg["title"],
                "description": layer_cfg.get("description", ""),
            }
            for layer_cfg in GURS_WMS_LAYERS.values()
        ]

    return {
        "success": True,
        "layers": layers,
        "wms_url": GURS_WMS_URL,
        "source": source,
    }


def _build_layer_payload(layer_id: str, layer_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": layer_id,
        "name": layer_cfg.get("name"),
        "title": layer_cfg.get("title", layer_id),
        "description": layer_cfg.get("description", ""),
        "url": layer_cfg.get("url", GURS_WMS_URL),
        "format": layer_cfg.get("format", "image/png"),
        "transparent": layer_cfg.get("transparent", True),
        "default_visible": layer_cfg.get("default_visible", False),
        "always_on": layer_cfg.get("always_on", False),
    }


def _parse_wms_capabilities(xml_text: str) -> List[Dict[str, Any]]:
    layers: List[Dict[str, Any]] = []
    try:
        tree = ET.fromstring(xml_text)
        ns = {"wms": "http://www.opengis.net/wms"}
        for layer in tree.findall(".//wms:Layer", ns):
            name = layer.findtext("wms:Name", default="", namespaces=ns)
            title = layer.findtext("wms:Title", default="", namespaces=ns)
            abstract = layer.findtext("wms:Abstract", default="", namespaces=ns)
            if not name:
                continue
            layers.append(
                {
                    "name": name,
                    "title": title or name,
                    "description": (abstract or "").strip(),
                }
            )
    except ET.ParseError as exc:
        logger.warning(f"[GURS] Napaka pri parsanju WMS Capabilities: {exc}")
    return layers


def _parse_query_for_parcel(query: str) -> tuple[str, Optional[str]]:
    ko_match = re.search(r"k\.?o\.?\s*([\w\-]+)", query, re.IGNORECASE)
    ko_hint = ko_match.group(1) if ko_match else None

    parcel_match = re.search(r"(\d+\s*/\s*\d+)", query)
    if parcel_match:
        parcel = parcel_match.group(1).replace(" ", "")
    else:
        digits = re.findall(r"\d+", query)
        if len(digits) >= 2:
            parcel = f"{digits[0]}/{digits[1]}"
        elif digits:
            parcel = digits[0]
        else:
            parcel = query

    return parcel, ko_hint


async def _search_parcel_via_wfs(parcel_no: str, ko_hint: Optional[str]) -> List[Dict[str, Any]]:
    features = await _fetch_parcel_features(parcel_no, ko_hint)
    if not features:
        return []

    results: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for feature in features:
        parcel_payload = _build_parcel_payload(feature)
        key = parcel_payload.get("stevilka")
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(parcel_payload)
        if len(results) >= 5:
            break

    return results


async def _fetch_parcel_features(parcel_no: str, ko_hint: Optional[str]) -> List[Dict[str, Any]]:
    parcel_no_clean = parcel_no.strip()
    if not parcel_no_clean:
        return []

    params_base = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "count": 5,
    }

    filter_candidates = []
    normalized = parcel_no_clean.replace(" ", "")
    filter_candidates.append(f"PARCELA='{normalized}'")
    filter_candidates.append(f"STEV_PARCE='{normalized.split('/')[-1]}'")
    filter_candidates.append(f"PARCELA LIKE '%{normalized}%'")

    if ko_hint:
        ko_clause = f"IME_KO ILIKE '{ko_hint}'"
    else:
        ko_clause = None

    type_names = [
        "kn:parcele",
        "kn:Parcele",
        "KN:PARCELA",
        "KN:Parcela",
    ]

    async with httpx.AsyncClient(timeout=GURS_API_TIMEOUT) as client:
        for type_name in type_names:
            for filter_clause in filter_candidates:
                params = params_base | {
                    "typeName": type_name,
                    "typeNames": type_name,
                    "cql_filter": f"{filter_clause}{' AND ' + ko_clause if ko_clause else ''}",
                }
                try:
                    response = await client.get(GURS_WFS_URL, params=params)
                    response.raise_for_status()
                    data = response.json()
                except Exception as exc:
                    logger.debug(
                        "[GURS] WFS poizvedba ni uspela (type=%s, filter=%s): %s",
                        type_name,
                        filter_clause,
                        exc,
                    )
                    continue

                features = data.get("features") or []
                if features:
                    logger.info(
                        "[GURS] Najdenih %s parcel prek WFS (type=%s)",
                        len(features),
                        type_name,
                    )
                    return features

    return []


def _build_parcel_payload(feature: Dict[str, Any]) -> Dict[str, Any]:
    props = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}

    parcel_no = (
        props.get("ST_PARCE")
        or props.get("STEV_PARCE")
        or props.get("PARCELA")
        or props.get("PARCELNO")
        or props.get("PARCEL_ST")
        or "Neznano"
    )

    ko_name = props.get("IME_KO") or props.get("KO") or props.get("NAZIV_KO") or "Ni podatka"

    povrsina = (
        props.get("POVRSINA")
        or props.get("AREA")
        or props.get("POVRSINA_M2")
        or 0
    )

    namenska_raba = (
        props.get("NAMENSKA_RABA")
        or props.get("NAM_RABA")
        or props.get("RABA")
        or "Ni podatka"
    )

    center = _geometry_centroid(geometry) or get_mock_coordinates(parcel_no)

    cache_key = _parcel_cache_key(parcel_no, ko_name)
    PARCEL_COORD_CACHE[cache_key] = center

    return {
        "stevilka": parcel_no,
        "katastrska_obcina": ko_name,
        "povrsina": povrsina,
        "namenska_raba": namenska_raba,
        "coordinates": center,
    }


def _geometry_centroid(geometry: Dict[str, Any]) -> Optional[List[float]]:
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if not coords:
        return None

    points = _flatten_coordinates(coords)
    if not points:
        return None

    lon = sum(pt[0] for pt in points) / len(points)
    lat = sum(pt[1] for pt in points) / len(points)
    return [lon, lat]


def _flatten_coordinates(data: Any) -> List[List[float]]:
    if isinstance(data, (list, tuple)):
        if data and isinstance(data[0], (float, int)):
            if len(data) >= 2:
                return [[float(data[0]), float(data[1])]]
            return []
        points: List[List[float]] = []
        for item in data:
            points.extend(_flatten_coordinates(item))
        return points
    return []


def _parcel_cache_key(parcel_no: str, ko: Optional[str]) -> str:
    return f"{parcel_no}:{(ko or '').strip().lower()}"


async def _resolve_parcel_coordinates(parcel_no: str, ko_hint: Optional[str]) -> List[float]:
    cache_key = _parcel_cache_key(parcel_no, ko_hint)
    if cache_key in PARCEL_COORD_CACHE:
        return PARCEL_COORD_CACHE[cache_key]

    coords: Optional[List[float]] = None

    if ENABLE_REAL_GURS_API:
        features = await _fetch_parcel_features(parcel_no, ko_hint)
        if features:
            coords = _geometry_centroid(features[0].get("geometry") or {})

    if not coords:
        coords = get_mock_coordinates(parcel_no)

    PARCEL_COORD_CACHE[cache_key] = coords
    return coords
