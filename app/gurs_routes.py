# app/gurs_routes.py
# POSODOBLJENA VERZIJA 2.1 (Popravki za delež rabe in osveževanje KO)

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Sequence

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
    GURS_RPE_WMS_URL,
    GURS_WFS_URL,
    GURS_WMS_LAYERS,
    GURS_WMS_URL,
    PROJECT_ROOT,
)
from .database import db_manager
from .schemas import MapStatePayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gurs", tags=["GURS"])

GURS_MAP_HTML = PROJECT_ROOT / "app" / "gurs_map.html"
# Spremenjeno: Boljši cache, ki hrani koordinate IN namensko rabo
PARCEL_DATA_CACHE: Dict[str, Dict[str, Any]] = {}

WMS_CAPABILITIES_TTL_SECONDS = 3600
WMS_CAPABILITIES_CACHE: Dict[str, Any] = {
    "layers": None,
    "fetched_at": 0.0,
}


@router.get("/map", response_class=HTMLResponse)
async def gurs_map_page():
    if not GURS_MAP_HTML.exists(): raise HTTPException(status_code=404, detail="GURS zemljevid ni na voljo")
    return GURS_MAP_HTML.read_text(encoding="utf-8")

@router.get("/map-config")
async def get_map_config(session_id: Optional[str] = None):
    saved_state_raw = await db_manager.fetch_map_state(session_id) if session_id else None
    saved_state = None
    if saved_state_raw: saved_state = {"center": [saved_state_raw["center_lon"], saved_state_raw["center_lat"]], "zoom": saved_state_raw["zoom"], "updated_at": saved_state_raw["updated_at"]}
    available_layers, _ = await _load_wms_capabilities()
    layer_lookup = {layer["name"]: layer for layer in available_layers if layer.get("name")}

    base_layers = [
        _build_layer_payload(id, cfg, available_layers, layer_lookup)
        for id, cfg in GURS_WMS_LAYERS.items()
        if cfg.get("category") == "base"
    ]
    overlay_layers = [
        _build_layer_payload(id, cfg, available_layers, layer_lookup)
        for id, cfg in GURS_WMS_LAYERS.items()
        if cfg.get("category") == "overlay"
    ]

    base_layers = [layer for layer in base_layers if layer]
    overlay_layers = [layer for layer in overlay_layers if layer]
    return {"success": True, "config": {"default_center": list(DEFAULT_MAP_CENTER), "default_zoom": DEFAULT_MAP_ZOOM, "wms_url": GURS_WMS_URL, "raster_wms_url": GURS_RASTER_WMS_URL, "rpe_wms_url": GURS_RPE_WMS_URL, "base_layers": base_layers, "overlay_layers": overlay_layers, "saved_state": saved_state}}

@router.get("/map-state/{session_id}")
async def get_map_state(session_id: str):
    state = await db_manager.fetch_map_state(session_id)
    if not state: return {"success": True, "state": None, "default_center": list(DEFAULT_MAP_CENTER), "default_zoom": DEFAULT_MAP_ZOOM}
    return {"success": True, "state": {"center": [state["center_lon"], state["center_lat"]], "zoom": state["zoom"], "updated_at": state["updated_at"]}}

@router.post("/map-state/{session_id}")
async def save_map_state(session_id: str, payload: MapStatePayload):
    session_id_clean = session_id.strip();
    if not session_id_clean: raise HTTPException(status_code=400, detail="Manjka session_id")
    await db_manager.save_map_state(session_id_clean, payload.center_lon, payload.center_lat, payload.zoom); return {"success": True}

@router.get("/search-parcel")
async def search_parcel(query: str = Query(..., description="Parcela številka (npr. 123/5 Hotič)")):
    logger.info(f"[GURS] Iskanje parcele: {query}"); query_clean = query.strip(); parcel_no, ko_hint = _parse_query_for_parcel(query_clean)
    if not parcel_no: raise HTTPException(status_code=400, detail="Vnesite vsaj številko parcele.")
    
    parcels: List[Dict[str, Any]] = []
    
    if ENABLE_REAL_GURS_API:
        logger.debug(f"[GURS] Iščem WFS: parcela='{parcel_no}', ko='{ko_hint}'")
        parcels_features = await _fetch_parcel_features(parcel_no, ko_hint)
        if parcels_features:
            parcels = [_build_parcel_payload(f) for f in parcels_features]
        else:
            parcels = []

    if not parcels:
        logger.debug("[GURS] WFS ni vrnil rezultatov ali ni vklopljen -> simulacija"); parcel_no = parcel_no or "123/4"
        mock_parcel = {"stevilka": parcel_no, "katastrska_obcina": ko_hint or "Simulirana KO", "coordinates": get_mock_coordinates(f"{parcel_no}-{ko_hint or ''}"), "povrsina": abs(hash(parcel_no) % 2000) + 500, "namenska_raba": "SSe (Simulirano)"}
        parcels = [mock_parcel]
        
    return {"success": True, "parcels": parcels}

@router.get("/session-parcels/{session_id}")
async def get_session_parcels(session_id: str):
    logger.info(f"[GURS] Pridobivam parcele za sejo: {session_id}"); data = await cache_manager.retrieve_session_data(session_id)
    if not data: raise HTTPException(status_code=404, detail="Seja ne obstaja ali je potekla")
    parcels = extract_parcels_from_session(data); logger.info(f"[GURS] Iz seje ekstrahiranih {len(parcels)} parcel")
    if not parcels: return {"success": True, "parcels": [], "message": "V dokumentih niso bile najdene parcele."}
    
    parcels_with_coords, not_found_count = [], 0
    
    for parcel in parcels:
        stevilka, ko = parcel.get("stevilka"), parcel.get("katastrska_obcina")
        if not stevilka: logger.warning(f"[GURS] Preskočena parcela brez številke: {parcel}"); continue

        parcel_details = await _resolve_parcel_details(stevilka, ko)
        
        is_mock = False
        if parcel_details:
            # === POPRAVEK: Uporabi celoten WFS payload ===
            # Shranimo originalno namensko rabo iz AI, če WFS ne vrne nič
            ai_namenska_raba = parcel.get("namenska_raba")
            
            # Posodobimo celoten "parcel" slovar s podatki iz WFS (tudi 'katastrska_obcina')
            parcel.update(parcel_details)
            
            # Če WFS ni vrnil namenske rabe (ker je 'Ni podatka...'), obdržimo tisto iz AI
            if parcel.get("namenska_raba", "Ni podatka").startswith("Ni podatka"):
                parcel["namenska_raba"] = ai_namenska_raba
            # === KONEC POPRAVKA ===
            
            # Preverimo, ali so koordinate morda mock
            mock_coords_key = _parcel_cache_key(stevilka, ko)
            mock_gen_coords = get_mock_coordinates(mock_coords_key)
            coords = parcel["coordinates"]
            if coords and len(coords) == 2 and len(mock_gen_coords) == 2:
                if abs(coords[0] - mock_gen_coords[0]) < 1e-9 and abs(coords[1] - mock_gen_coords[1]) < 1e-9:
                    is_mock = True
        else:
            # WFS ni našel nič, uporabimo mock koordinate
            parcel["coordinates"] = get_mock_coordinates(_parcel_cache_key(stevilka, ko))
            is_mock = True

        if is_mock:
            logger.warning(f"[GURS] Parcela {stevilka} (KO: {ko or 'N/A'}) ni najdena z WFS -> mock koordinate.")
            not_found_count += 1
            
        parcels_with_coords.append(parcel)
        # Logiramo posodobljeno ime KO
        logger.info(f"[GURS] Parcela {stevilka} (KO: {parcel.get('katastrska_obcina') or 'N/A'}): Koordinate {parcel.get('coordinates')}{' (Mock)' if is_mock else ''}, Raba: {parcel.get('namenska_raba')}")

    message = f"Opozorilo: Za {not_found_count} od {len(parcels)} parcel ni bilo mogoče pridobiti točne lokacije." if not_found_count > 0 else None
    return {"success": True, "parcels": parcels_with_coords, "message": message}


def extract_parcels_from_session(session_data: Dict[str, Any]) -> List[Dict[str, str]]:
    parcels = []; key_data = session_data.get("key_data", {})
    if not key_data: logger.warning("[GURS] Manjka 'key_data'."); return []
    logger.debug(f"[GURS] Ekstrahiram parcele iz: {list(key_data.keys())}"); gradbena_parcela, vse_parcele_str, velikost_str = key_data.get("parcela_objekta", "").strip(), key_data.get("stevilke_parcel_ko", "").strip(), key_data.get("velikost_parcel", "").strip()
    logger.debug(f"[GURS] Raw Gradbena: '{gradbena_parcela}', Vse: '{vse_parcele_str}', Velikost: '{velikost_str}'")
    ko_match = re.search(r"k\.?o\.?\s*([\w\s\-]+)", vse_parcele_str, re.IGNORECASE); katastrska_obcina = ko_match.group(1).strip() if ko_match else None
    if not katastrska_obcina and gradbena_parcela: ko_match_grad = re.search(r"k\.?o\.?\s*([\w\s\-]+)", gradbena_parcela, re.IGNORECASE); katastrska_obcina = ko_match_grad.group(1).strip() if ko_match_grad else None
    katastrska_obcina = katastrska_obcina or None; logger.info(f"[GURS] Ugotovljena KO: '{katastrska_obcina}'")
    
    ai_details = session_data.get("ai_details", {}); namenska_raba_list = ai_details.get("namenska_raba", []); 
    namenska_raba = namenska_raba_list[0] if namenska_raba_list else "Ni podatka"
    logger.info(f"[GURS] Namenska raba (iz AI): '{namenska_raba}'")
    
    velikost_int = 0
    try:
        velikost_match = re.search(r"(\d+[\.,]?\d*)", velikost_str);
        if velikost_match: velikost_int = int(float(velikost_match.group(1).replace(',', '.')))
        else: numbers = re.findall(r"(\d+[\.,]?\d*)", velikost_str); velikost_int = sum(int(float(n.replace(',', '.'))) for n in numbers) if numbers else 0
    except Exception as e: logger.warning(f"[GURS] Napaka pri parsanju velikosti '{velikost_str}': {e}")
    logger.info(f"[GURS] Parsana skupna velikost: {velikost_int} m²")
    
    parcela_numbers = []
    if vse_parcele_str:
        parcele_brez_ko = re.sub(r"k\.?o\.?.*", "", vse_parcele_str, flags=re.IGNORECASE).strip()
        logger.debug(f"[GURS] Parcele brez K.O.: '{parcele_brez_ko}'")
        raw_parts = re.split(r'[,;\s]+', parcele_brez_ko)
        for p in raw_parts:
            p_clean = p.strip()
            if p_clean and re.search(r'\d', p_clean):
                p_final = re.match(r'^([\d/]+)', p_clean)
                if p_final:
                    parcela_numbers.append(p_final.group(1))
        parcela_numbers = [p for p in parcela_numbers if p] 
    logger.info(f"[GURS] Najdene parcele iz 'vse parcele': {parcela_numbers}")
    
    if parcela_numbers:
        povrsina_per_parcel = (velikost_int // len(parcela_numbers)) if velikost_int > 0 and len(parcela_numbers) > 0 else 0
        for parcela_num in parcela_numbers: parcels.append({"stevilka": parcela_num, "katastrska_obcina": katastrska_obcina, "povrsina": povrsina_per_parcel, "namenska_raba": namenska_raba})
    elif gradbena_parcela:
        gradbena_brez_ko = re.sub(r"k\.?o\.?.*", "", gradbena_parcela, flags=re.IGNORECASE).strip(); gradbena_match = re.match(r'^([\d/]+)', gradbena_brez_ko)
        if gradbena_match: parcela_num = gradbena_match.group(1); logger.info(f"[GURS] Uporabljam gradbeno parcelo: '{parcela_num}'"); parcels.append({"stevilka": parcela_num, "katastrska_obcina": katastrska_obcina, "povrsina": velikost_int, "namenska_raba": namenska_raba})
        else: logger.warning(f"[GURS] Gradbena parcela '{gradbena_parcela}' nima prepoznavne številke.")
    
    unique_parcels, seen = [], set()
    for p in parcels:
        key = (p.get('stevilka'), p.get('katastrska_obcina'))
        if key not in seen:
            unique_parcels.append(p)
            seen.add(key)
        else:
            logger.debug(f"[GURS] Odstranjen duplikat: {p.get('stevilka')} KO: {p.get('katastrska_obcina')}")
    
    logger.info(f"[GURS] === Končni seznam parcel: {len(unique_parcels)} ===")
    for i, p in enumerate(unique_parcels, 1): logger.info(f"[GURS] Parcela {i}: {p.get('stevilka')} (KO: {p.get('katastrska_obcina') or 'N/A'}) Pov.: {p.get('povrsina')}")
    return unique_parcels

def get_mock_coordinates(parcela_key: str) -> List[float]:
    base_lon, base_lat = 14.8267, 46.0569; hash_val = abs(hash(parcela_key))
    offset_lon, offset_lat = ((hash_val % 4000) - 2000) * 0.00002, (((hash_val // 4000) % 4000) - 2000) * 0.00002
    lon, lat = base_lon + offset_lon, base_lat + offset_lon
    logger.debug(f"[GURS] Mock koordinate za '{parcela_key}': [{lon:.6f}, {lat:.6f}]"); return [lon, lat]

@router.get("/parcel-info/{parcela_st}")
async def get_parcel_info(parcela_st: str, ko: Optional[str] = Query(None, description="Katastrska občina")):
    logger.info(f"[GURS] Info za parcelo: {parcela_st}, K.O.: {ko}")
    if ENABLE_REAL_GURS_API:
        parcels_features = await _fetch_parcel_features(parcela_st, ko)
        if parcels_features: 
            return {"success": True, "parcel": _build_parcel_payload(parcels_features[0])}
        else: 
            logger.warning(f"WFS ni našel {parcela_st} (KO: {ko}) za podrobnosti.")
            
    mock_key = f"{parcela_st}-{ko or ''}"
    return {"success": True, "parcel": {"stevilka": parcela_st, "katastrska_obcina": ko or "Simulirana KO", "povrsina": abs(hash(parcela_st) % 2000) + 500, "namenska_raba": "SSe (Simulirano)", "lastniki": "Zaščiteno (Simulirano)", "obremenjenja": "Ni (Simulirano)", "coordinates": get_mock_coordinates(mock_key)},
        "message": "Uporabljeni simulirani podatki." if not ENABLE_REAL_GURS_API else "Parcela ni najdena -> simulirani podatki."}

@router.get("/wms-capabilities")
async def get_wms_capabilities(refresh: bool = Query(False, description="Prisili ponovno poizvedbo")):
    layers, source = await _load_wms_capabilities(force_refresh=refresh)
    if not layers:
        fallback_layers = [
            {"name": cfg.get("name", id), "title": cfg.get("title", id), "description": cfg.get("description", "")}
            for id, cfg in GURS_WMS_LAYERS.items()
            if cfg.get("name") or cfg.get("name_candidates")
        ]
        logger.info(f"[GURS] GetCapabilities ni na voljo -> {len(fallback_layers)} fallback slojev.")
        return {"success": True, "layers": fallback_layers, "wms_url": GURS_WMS_URL, "source": "fallback"}

    return {"success": True, "layers": layers, "wms_url": GURS_WMS_URL, "source": source}

def _build_layer_payload(
    layer_id: str,
    layer_cfg: Dict[str, Any],
    available_layers: Sequence[Dict[str, Any]] | None,
    available_lookup: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    selected_layer = _select_layer_metadata(layer_id, layer_cfg, available_layers, available_lookup)
    if not selected_layer:
        logger.warning(f"[GURS] Sloj '{layer_id}' nima veljavnega imena -> preskočen.")
        return None

    selected_name = selected_layer.get("name")
    if not selected_name:
        logger.warning(f"[GURS] Sloj '{layer_id}' nima določenega imena -> preskočen.")
        return None

    if layer_cfg.get("name") and selected_name != layer_cfg.get("name"):
        logger.debug(
            "[GURS] Sloj '%s' uporablja dinamično ime '%s' (namesto '%s').",
            layer_id,
            selected_name,
            layer_cfg.get("name"),
        )

    default_url = GURS_WMS_URL
    if layer_id == "ortofoto":
        default_url = GURS_RASTER_WMS_URL
    elif layer_id == "namenska_raba":
        default_url = GURS_RPE_WMS_URL  # Popravljeno: Ta sloj uporablja RPE URL

    title = layer_cfg.get("title") or selected_layer.get("title") or layer_id
    description = layer_cfg.get("description") or selected_layer.get("description", "")

    payload = {
        "id": layer_id,
        "name": selected_name,
        "title": title,
        "description": description,
        "url": layer_cfg.get("url", default_url),
        "format": layer_cfg.get("format", "image/png"),
        "transparent": layer_cfg.get("transparent", True),
        "default_visible": layer_cfg.get("default_visible", False),
        "always_on": layer_cfg.get("always_on", False),
        "category": layer_cfg.get("category", "overlay"),
    }

    if "opacity" in layer_cfg:
        payload["opacity"] = layer_cfg["opacity"]

    return payload

def _parse_wms_capabilities(xml_text: str) -> List[Dict[str, Any]]:
    layers: List[Dict[str, Any]] = []
    try:
        xml_text = re.sub(' xmlns="[^"]+"', '', xml_text, count=1); tree = ET.fromstring(xml_text); namespaces = {'wms': 'http://www.opengis.net/wms'}
        capability_node = tree.find('.//wms:Capability', namespaces) or tree.find('.//Capability')
        if capability_node is None: logger.warning("XML nima 'Capability'."); return []
        for layer_node in capability_node.findall('.//wms:Layer', namespaces) or capability_node.findall('.//Layer'):
            name_node = layer_node.find('wms:Name', namespaces) or layer_node.find('Name'); title_node = layer_node.find('wms:Title', namespaces) or layer_node.find('Title'); abstract_node = layer_node.find('wms:Abstract', namespaces) or layer_node.find('Abstract')
            if name_node is not None and name_node.text: name = name_node.text.strip(); title = title_node.text.strip() if title_node is not None and title_node.text else name; abstract = abstract_node.text.strip() if abstract_node is not None and abstract_node.text else ""; layers.append({"name": name, "title": title, "description": abstract})
    except ET.ParseError as exc: logger.error(f"[GURS] Napaka parsanja WMS XML: {exc}", exc_info=True)
    except Exception as exc: logger.error(f"[GURS] Nepričakovana napaka parsanja WMS XML: {exc}", exc_info=True)
    logger.debug(f"Parsanih {len(layers)} slojev iz XML."); return layers


async def _load_wms_capabilities(force_refresh: bool = False) -> tuple[List[Dict[str, Any]], str]:
    """Naloži WMS sloje iz GetCapabilities z osnovnim cachingom."""

    now = time.monotonic()
    cached_layers = WMS_CAPABILITIES_CACHE.get("layers") or []
    cached_age = now - WMS_CAPABILITIES_CACHE.get("fetched_at", 0.0)

    if cached_layers and not force_refresh and cached_age < WMS_CAPABILITIES_TTL_SECONDS:
        logger.debug("[GURS] Uporabljam cache WMS slojev (%d slojev, starost %.0fs).", len(cached_layers), cached_age)
        return cached_layers, "cache"

    target_wms_url = GURS_WMS_URL
    try:
        async with httpx.AsyncClient(timeout=GURS_API_TIMEOUT) as client:
            logger.debug(f"Zahtevam GetCapabilities z: {target_wms_url}")
            response = await client.get(
                target_wms_url,
                params={"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"},
            )
            response.raise_for_status()
            logger.debug(f"GetCapabilities OK: {response.status_code}")
            layers = _parse_wms_capabilities(response.text)
            if layers:
                WMS_CAPABILITIES_CACHE["layers"] = layers
                WMS_CAPABILITIES_CACHE["fetched_at"] = now
                logger.info(f"[GURS] Naloženih {len(layers)} WMS slojev (osveženo).")
                return layers, "remote"
            logger.warning("[GURS] GetCapabilities vrnil brez slojev.")
    except Exception as exc:
        logger.warning(f"[GURS] GetCapabilities ni uspel ({target_wms_url}): {exc}")

    if cached_layers:
        logger.debug("[GURS] Uporabljam prejšnji cache (%d slojev).", len(cached_layers))
        return cached_layers, "cache"

    return [], "error"


def _select_layer_metadata(
    layer_id: str,
    layer_cfg: Dict[str, Any],
    available_layers: Sequence[Dict[str, Any]] | None,
    available_lookup: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if available_lookup is None:
        available_lookup = {}

    candidates: List[str] = []
    name_explicit = layer_cfg.get("name")
    if name_explicit:
        candidates.append(name_explicit)
    candidates.extend(layer_cfg.get("name_candidates", []))

    for candidate in candidates:
        if candidate and candidate in available_lookup:
            return available_lookup[candidate]

    if available_layers:
        keywords = [kw.lower() for kw in layer_cfg.get("title_keywords", []) if isinstance(kw, str)]
        if keywords:
            for layer in available_layers:
                combined = f"{layer.get('title', '')} {layer.get('name', '')}".lower()
                if all(keyword in combined for keyword in keywords):
                    logger.debug(
                        "[GURS] Sloj '%s' ujemanje po ključnih besedah -> %s",
                        layer_id,
                        layer.get("name"),
                    )
                    return layer

        pattern = layer_cfg.get("name_regex")
        if pattern:
            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                logger.warning(
                    "[GURS] Neveljaven regex '%s' za sloj '%s': %s",
                    pattern,
                    layer_id,
                    exc,
                )
            else:
                for layer in available_layers:
                    if compiled.search(layer.get("name", "")):
                        logger.debug(
                            "[GURS] Sloj '%s' ujemanje po regexu -> %s",
                            layer_id,
                            layer.get("name"),
                        )
                        return layer

        prefix = layer_cfg.get("name_prefix")
        if prefix:
            for layer in available_layers:
                if layer.get("name", "").startswith(prefix):
                    logger.debug(
                        "[GURS] Sloj '%s' ujemanje po prefiksu -> %s",
                        layer_id,
                        layer.get("name"),
                    )
                    return layer

    fallback_name = name_explicit or (layer_cfg.get("name_candidates") or [None])[0]
    if fallback_name:
        return {"name": fallback_name}

    logger.warning(f"[GURS] Sloj '{layer_id}' nima določljivih imen.")
    return None

def _parse_query_for_parcel(query: str) -> tuple[Optional[str], Optional[str]]:
    query = query.strip()
    if not query:
        return None, None

    parcel_no: Optional[str] = None
    ko_hint: Optional[str] = None

    ko_match = re.search(r"k\.?o\.?\s*([\w\s\-]+)", query, re.IGNORECASE)
    if ko_match:
        ko_hint = ko_match.group(1).strip()
        query_without_ko = (query[: ko_match.start()] + " " + query[ko_match.end() :]).strip()
    else:
        query_without_ko = query

    numbers = re.findall(r"\d+(?:/\d+)?", query_without_ko)

    if not ko_hint and numbers:
        first_number = numbers[0]
        remaining = numbers[1:]
        if len(first_number) in {3, 4, 5} and "/" not in first_number and remaining:
            ko_hint = first_number
            parcel_no = remaining[0]
        else:
            parcel_no = first_number
    elif numbers:
        parcel_no = numbers[0]

    if not parcel_no and len(numbers) >= 2:
        parcel_no = numbers[-1]

    if parcel_no:
        parcel_no = parcel_no.replace(" ", "").strip()
        parcel_no = re.sub(r"[.,]$", "", parcel_no)

    logger.debug(f"Parsano iz '{query}': parcela='{parcel_no}', ko='{ko_hint}'")
    return parcel_no, ko_hint

def _extract_ko_id(ko_hint: Optional[str]) -> Optional[int]:
    if not ko_hint:
        return None
    match = re.search(r'(\d{3,5})$', ko_hint.strip()) 
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    match = re.search(r'(\d{3,5})', ko_hint.strip()) 
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    logger.warning(f"[GURS] Iz 'ko_hint' ('{ko_hint}') ni bilo mogoče ekstrahirati KO_ID.")
    return None

async def _fetch_parcel_land_use(eid_parcela: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    if not eid_parcela:
        logger.warning("[GURS] WFS Namenska Raba: Manjka EID_PARCELA.")
        return []
    
    type_name = "SI.GURS.KN:PARCELE_X_NAMENSKE_RABE_TABELA"
    eid_parcela_escaped = eid_parcela.replace("'", "''")
    cql_filter = f"EID_PARCELA='{eid_parcela_escaped}'"
    
    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326", 
        "typeName": type_name,
        "cql_filter": cql_filter,
        "count": 10 
    }
    
    try:
        logger.debug(f"[GURS] WFS Poizvedba (Namenska Raba): Filter={cql_filter}")
        response = await client.get(GURS_WFS_URL, params=params)
        
        if response.status_code == 400:
            logger.warning(f"[GURS] WFS Namenska Raba 400 Bad Request: {response.text[:200]}")
            return []
            
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        
        if features:
            logger.info(f"[GURS] Najdenih {len(features)} namenskih rab za EID_PARCELA={eid_parcela}")
            return features
        else:
            logger.debug(f"[GURS] Ni namenskih rab za EID_PARCELA={eid_parcela}")
            return []
            
    except httpx.HTTPStatusError as exc:
        logger.warning(f"[GURS] WFS Namenska Raba HTTPStatusError {exc.response.status_code}: {exc.response.text[:200]}")
        return []
    except Exception as exc:
        logger.error(f"[GURS] WFS Namenska Raba Splošna napaka: {exc}", exc_info=True)
        return []

async def _fetch_parcel_features(parcel_no: str, ko_hint: Optional[str]) -> List[Dict[str, Any]]:
    parcel_no_clean = parcel_no.strip().replace(" ", "")
    if not parcel_no_clean: 
        return []

    params_base = {
        "service": "WFS", 
        "request": "GetFeature", 
        "version": "2.0.0",
        "outputFormat": "application/json", 
        "srsName": "EPSG:4326", 
        "count": 15
    }

    cql_filter_parts = []
    
    if parcel_no_clean:
        cql_filter_parts.append(f"ST_PARCELE='{parcel_no_clean}'")
        logger.debug(f"WFS Filter: Uporabljam ST_PARCELE='{parcel_no_clean}'")
    else:
        logger.warning("[GURS] WFS: Manjka številka parcele za filter.")
        return []
        
    ko_id_num = _extract_ko_id(ko_hint)
    if ko_id_num:
        cql_filter_parts.append(f"KO_ID={ko_id_num}") 
        logger.debug(f"WFS Filter: Dodajam KO_ID={ko_id_num} (iz '{ko_hint}')")
    elif ko_hint:
        logger.warning(f"[GURS] WFS: 'ko_hint' ('{ko_hint}') je podan, a KO_ID ni bil ekstrahiran. Iščem samo po št. parcele, kar morda vrne preveč zadetkov.")
        
    if not cql_filter_parts: 
        logger.warning("[GURS] WFS: Ni filtra.")
        return []
        
    full_cql_filter = " AND ".join(cql_filter_parts)
    type_name = "SI.GURS.KN:PARCELE_TABELA" 

    async with httpx.AsyncClient(timeout=GURS_API_TIMEOUT) as client:
        params = params_base | {
            "typeName": type_name, 
            "typeNames": type_name, 
            "cql_filter": full_cql_filter
        }
        try:
            logger.debug(f"[GURS] WFS Poizvedba (Parcela): URL={GURS_WFS_URL}, Params={params}")
            response = await client.get(GURS_WFS_URL, params=params)
            
            if response.status_code == 400:
                error_text = "Neznana napaka"
                try:
                    root = ET.fromstring(response.text)
                    ns = {'ows': 'http://www.opengis.net/ows/1.1'}
                    exception_node = root.find('.//ows:ExceptionText', ns)
                    if exception_node is not None and exception_node.text:
                        error_text = exception_node.text.strip()
                except ET.ParseError:
                    error_text = response.text[:200].strip()

                logger.warning(f"[GURS] WFS 400 Bad Request: Type={type_name}, Filter={full_cql_filter}, Napaka: {error_text}")
                return []
            
            response.raise_for_status()
            data = response.json()
            features = data.get("features", [])
            
            if features:
                logger.info(f"[GURS] Najdenih {len(features)} parcel prek WFS. Pridobivam namensko rabo zanjo...")
                
                for feature in features:
                    props = feature.get("properties", {})
                    eid_parcela = props.get("EID_PARCELA")
                    
                    if eid_parcela:
                        land_use_features = await _fetch_parcel_land_use(eid_parcela, client)
                        
                        if land_use_features:
                            land_use_parts = []
                            for lu_feat in land_use_features:
                                lu_props = lu_feat.get("properties", {})
                                lu_id = lu_props.get("VRSTA_NAMENSKE_RABE_ID")
                                lu_delez_raw = lu_props.get("DELEZ")
                                
                                # === POPRAVEK: Iz "1000%" v "100%" ===
                                # Vrednost 'DELEZ' je očitno že v procentih (npr. 100.0), ne 0-1 (npr. 1.0)
                                lu_delez_str = f"{float(lu_delez_raw):.0f}%" if lu_delez_raw is not None else "N/A"
                                # === KONEC POPRAVKA ===

                                land_use_parts.append(f"ID: {lu_id} ({lu_delez_str})")
                            
                            props["namenska_raba_wfs"] = ", ".join(land_use_parts)
                            logger.debug(f"Namenska raba za {eid_parcela}: {props['namenska_raba_wfs']}")
                        else:
                            props["namenska_raba_wfs"] = "Ni podatka (WFS)"
                    else:
                        props["namenska_raba_wfs"] = "Manjka EID_PARCELA"

                return features 
            
            else: 
                logger.debug(f"[GURS] WFS OK, 0 zadetkov (Type={type_name}, Filter={full_cql_filter})")
                
        except httpx.HTTPStatusError as exc: 
            logger.warning(f"[GURS] WFS HTTPStatusError {exc.response.status_code} (Type={type_name}, Filter={full_cql_filter}): {exc.response.text[:500]}")
        except Exception as exc: 
            logger.error(f"[GURS] WFS Splošna napaka (Type={type_name}, Filter={full_cql_filter}): {exc}", exc_info=True)

    logger.warning(f"[GURS] WFS poizvedba ni vrnila rezultatov za filter: {full_cql_filter}")
    return []

def _build_parcel_payload(feature: Dict[str, Any]) -> Dict[str, Any]:
    props = feature.get("properties") or {}; geometry = feature.get("geometry") or {}
    
    parcel_no = props.get("ST_PARCELE") or "Neznano"  
    ko_id = props.get("KO_ID") 
    
    # Tukaj nastavimo ime KO, ki bo uporabljeno povsod
    ko_name = f"KO ID: {ko_id}" if ko_id else "Ni podatka"
    
    povrsina = props.get("POVRSINA") or 0
    namenska_raba = props.get("namenska_raba_wfs") or "Ni podatka (WFS)" 
    
    center = _geometry_centroid(geometry)
    
    cache_key = _parcel_cache_key(parcel_no, str(ko_id) if ko_id else "unknown_ko")
    
    if not center: 
        logger.warning(f"Ni centra za {parcel_no}, mock."); 
        center = get_mock_coordinates(cache_key) 
    
    payload = {
        "stevilka": parcel_no, 
        "katastrska_obcina": ko_name,
        "povrsina": int(povrsina) if povrsina else 0, 
        "namenska_raba": namenska_raba, 
        "coordinates": center
    }
    PARCEL_DATA_CACHE[cache_key] = payload 
    
    return payload


def _geometry_centroid(geometry: Dict[str, Any]) -> Optional[List[float]]:
    geom_type, coords = geometry.get("type"), geometry.get("coordinates")
    if not geom_type or not coords: return None
    try:
        if geom_type == "Point": return [float(coords[0]), float(coords[1])] if len(coords) >= 2 and all(isinstance(c, (float, int)) for c in coords[:2]) else None
        elif geom_type in ["Polygon", "MultiPolygon"]:
            points = _flatten_coordinates(coords); num_points = len(points);
            if num_points == 0: return None
            sum_lon, sum_lat = sum(pt[0] for pt in points), sum(pt[1] for pt in points);
            return [sum_lon / num_points, sum_lat / num_points] if num_points > 0 else None
        else: logger.warning(f"Nepodprt tip geometrije: {geom_type}"); return None
    except Exception as e: logger.error(f"Napaka pri centroidu: {e}", exc_info=True); return None

def _flatten_coordinates(data: Any) -> List[List[float]]:
    points: List[List[float]] = []
    if isinstance(data, (list, tuple)):
        if len(data) >= 2 and all(isinstance(x, (int, float)) for x in data[:2]): points.append([float(data[0]), float(data[1])])
        else:
            for item in data: points.extend(_flatten_coordinates(item))
    return points

def _parcel_cache_key(parcel_no: str, ko: Optional[str]) -> str:
    ko_safe = (ko or "unknown").strip().lower(); 
    parcel_safe = (parcel_no or "unknown").strip(); 
    return f"{parcel_safe}::{ko_safe}"

async def _resolve_parcel_details(parcel_no: str, ko_hint: Optional[str]) -> Optional[Dict[str, Any]]:
    if not parcel_no: 
        logger.warning("Pridobivam podrobnosti brez št. parcele."); 
        return None 

    cache_key = _parcel_cache_key(parcel_no, ko_hint)
    
    if cache_key in PARCEL_DATA_CACHE: 
        logger.debug(f"Podatki za '{cache_key}' iz cache."); 
        return PARCEL_DATA_CACHE[cache_key]

    ko_id_str = str(_extract_ko_id(ko_hint) or ko_hint or "unknown")
    cache_key_id = _parcel_cache_key(parcel_no, ko_id_str)

    if cache_key_id in PARCEL_DATA_CACHE:
        logger.debug(f"Podatki za '{cache_key_id}' (z ID) iz cache.");
        return PARCEL_DATA_CACHE[cache_key_id]

    payload: Optional[Dict[str, Any]] = None
    
    if ENABLE_REAL_GURS_API:
        logger.debug(f"Iščem podrobnosti za '{cache_key}' preko WFS...")
        features = await _fetch_parcel_features(parcel_no, ko_hint)
        if features:
            payload = _build_parcel_payload(features[0]) 
            if payload:
                logger.info(f"Podatki za '{cache_key}' iz WFS.")
            else:
                logger.warning(f"WFS vrnil parcelo za '{cache_key}', a payload ni bil zgrajen.")
        else: 
            logger.warning(f"WFS ni našel parcele za '{cache_key}'.")
            
    if not payload: 
        logger.debug(f"Uporabljam mock payload za '{cache_key}'.")
        mock_coords = get_mock_coordinates(cache_key)
        payload = {
            "stevilka": parcel_no,
            "katastrska_obcina": ko_hint or "Simulirana KO",
            "povrsina": 0, 
            "namenska_raba": "Ni podatka (Mock)",
            "coordinates": mock_coords
        }
        PARCEL_DATA_CACHE[cache_key] = payload
        PARCEL_DATA_CACHE[cache_key_id] = payload

    return payload