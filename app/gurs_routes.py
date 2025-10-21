# app/gurs_routes.py
# POSODOBLJENA VERZIJA (z POENOSTAVLJENIM 'PARCELA' filtrom v WFS)

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
PARCEL_COORD_CACHE: Dict[str, List[float]] = {}

@router.get("/map", response_class=HTMLResponse)
async def gurs_map_page():
    if not GURS_MAP_HTML.exists(): raise HTTPException(status_code=404, detail="GURS zemljevid ni na voljo")
    return GURS_MAP_HTML.read_text(encoding="utf-8")

@router.get("/map-config")
async def get_map_config(session_id: Optional[str] = None):
    saved_state_raw = await db_manager.fetch_map_state(session_id) if session_id else None
    saved_state = None
    if saved_state_raw: saved_state = {"center": [saved_state_raw["center_lon"], saved_state_raw["center_lat"]], "zoom": saved_state_raw["zoom"], "updated_at": saved_state_raw["updated_at"]}
    base_layers = [_build_layer_payload(id, cfg) for id, cfg in GURS_WMS_LAYERS.items() if cfg.get("category") == "base"]
    overlay_layers = [_build_layer_payload(id, cfg) for id, cfg in GURS_WMS_LAYERS.items() if cfg.get("category") == "overlay"]
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
        if parcel_no and ko_hint: logger.debug(f"[GURS] Iščem WFS: parcela='{parcel_no}', ko='{ko_hint}'"); parcels = await _search_parcel_via_wfs(parcel_no, ko_hint)
        elif parcel_no: logger.debug(f"[GURS] Iščem WFS samo po parceli: '{parcel_no}'"); parcels = await _search_parcel_via_wfs(parcel_no, None)
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
        coords = await _resolve_parcel_coordinates(stevilka, ko)
        mock_coords_key = _parcel_cache_key(stevilka, ko)
        is_mock, mock_gen_coords = False, get_mock_coordinates(mock_coords_key)
        if coords and len(coords) == 2 and len(mock_gen_coords) == 2:
             if abs(coords[0] - mock_gen_coords[0]) < 1e-9 and abs(coords[1] - mock_gen_coords[1]) < 1e-9: is_mock = True
        if is_mock: logger.warning(f"[GURS] Parcela {stevilka} (KO: {ko or 'N/A'}) ni najdena z WFS -> mock koordinate."); not_found_count += 1
        parcel["coordinates"] = coords; parcels_with_coords.append(parcel)
        logger.info(f"[GURS] Parcela {stevilka} (KO: {ko or 'N/A'}): Koordinate {coords}{' (Mock)' if is_mock else ''}")
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
    ai_details = session_data.get("ai_details", {}); namenska_raba_list = ai_details.get("namenska_raba", []); namenska_raba = namenska_raba_list[0] if namenska_raba_list else "Ni podatka"
    logger.info(f"[GURS] Namenska raba: '{namenska_raba}'")
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
    lon, lat = base_lon + offset_lon, base_lat + offset_lat
    logger.debug(f"[GURS] Mock koordinate za '{parcela_key}': [{lon:.6f}, {lat:.6f}]"); return [lon, lat]

@router.get("/parcel-info/{parcela_st}")
async def get_parcel_info(parcela_st: str, ko: Optional[str] = Query(None, description="Katastrska občina")):
    logger.info(f"[GURS] Info za parcelo: {parcela_st}, K.O.: {ko}")
    if ENABLE_REAL_GURS_API:
        parcels = await _search_parcel_via_wfs(parcela_st, ko)
        if parcels: return {"success": True, "parcel": parcels[0]}
        else: logger.warning(f"WFS ni našel {parcela_st} (KO: {ko}) za podrobnosti.")
    mock_key = f"{parcela_st}-{ko or ''}"
    return {"success": True, "parcel": {"stevilka": parcela_st, "katastrska_obcina": ko or "Simulirana KO", "povrsina": abs(hash(parcela_st) % 2000) + 500, "namenska_raba": "SSe (Simulirano)", "lastniki": "Zaščiteno (Simulirano)", "obremenjenja": "Ni (Simulirano)", "coordinates": get_mock_coordinates(mock_key)},
        "message": "Uporabljeni simulirani podatki." if not ENABLE_REAL_GURS_API else "Parcela ni najdena -> simulirani podatki."}

@router.get("/wms-capabilities")
async def get_wms_capabilities():
    layers, source, target_wms_url = [], "remote", GURS_WMS_URL
    try:
        async with httpx.AsyncClient(timeout=GURS_API_TIMEOUT) as client:
            logger.debug(f"Zahtevam GetCapabilities z: {target_wms_url}"); response = await client.get(target_wms_url, params={"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"})
            response.raise_for_status(); logger.debug(f"GetCapabilities OK: {response.status_code}"); layers = _parse_wms_capabilities(response.text); logger.info(f"Parsanih {len(layers)} slojev.")
    except Exception as exc: source = "fallback"; logger.warning(f"[GURS] GetCapabilities ni uspel ({target_wms_url}): {exc}"); layers = [{"name": cfg.get("name", id), "title": cfg.get("title", id), "description": cfg.get("description", "")} for id, cfg in GURS_WMS_LAYERS.items() if cfg.get("name")]; logger.info(f"Uporabljam {len(layers)} fallback slojev.")
    return {"success": True, "layers": layers, "wms_url": target_wms_url, "source": source}

def _build_layer_payload(layer_id: str, layer_cfg: Dict[str, Any]) -> Dict[str, Any]:
    default_url = GURS_WMS_URL;
    if layer_id == 'ortofoto': default_url = GURS_RASTER_WMS_URL
    # elif layer_id == 'namenska_raba': default_url = GURS_RPE_WMS_URL # Ne več
    return {"id": layer_id, "name": layer_cfg.get("name"), "title": layer_cfg.get("title", layer_id), "description": layer_cfg.get("description", ""), "url": layer_cfg.get("url", default_url), "format": layer_cfg.get("format", "image/png"), "transparent": layer_cfg.get("transparent", True), "default_visible": layer_cfg.get("default_visible", False), "always_on": layer_cfg.get("always_on", False), "category": layer_cfg.get("category", "overlay")}

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

def _parse_query_for_parcel(query: str) -> tuple[Optional[str], Optional[str]]:
    query = query.strip(); parcel_no, ko_hint = None, None; ko_match = re.search(r"k\.?o\.?\s*([\w\s\-]+)", query, re.IGNORECASE)
    if ko_match: ko_hint = ko_match.group(1).strip(); query_without_ko = query[:ko_match.start()].strip() + query[ko_match.end():].strip()
    else: query_without_ko = query
    parcel_match = re.search(r"(\d[\d\s/]*\d|\d+)", query_without_ko)
    if parcel_match: parcel_no = parcel_match.group(1).replace(" ", "").strip()
    if parcel_no: parcel_no = re.sub(r'[.,]$', '', parcel_no)
    logger.debug(f"Parsano iz '{query}': parcela='{parcel_no}', ko='{ko_hint}'"); return parcel_no, ko_hint

# === POPRAVLJENA FUNKCIJA _fetch_parcel_features (samo PARCELA filter) ===
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

    # === POPRAVLJEN FILTER - uporabi ST_PARCE namesto PARCELA ===
    cql_filter_parts = []
    if parcel_no_clean:
        cql_filter_parts.append(f"ST_PARCE='{parcel_no_clean}'")  # ✅ POPRAVLJENO
        logger.debug(f"WFS Filter: Uporabljam ST_PARCE='{parcel_no_clean}'")
    else:
        logger.warning("[GURS] WFS: Manjka številka parcele za filter.")
        return []
        
    # Dodaj filter po KO, če je podan
    if ko_hint:
        ko_clean = ko_hint.strip()
        ko_escaped = ko_clean.replace("'", "''")
        cql_filter_parts.append(f"IME_KO='{ko_escaped}'")
        logger.debug(f"WFS Filter: Dodajam IME_KO='{ko_escaped}'")
        
    if not cql_filter_parts: 
        logger.warning("[GURS] WFS: Ni filtra.")
        return []
        
    full_cql_filter = " AND ".join(cql_filter_parts)

    type_names = ["SI.GURS.KN:PARCELE"]

    async with httpx.AsyncClient(timeout=GURS_API_TIMEOUT) as client:
        for type_name in type_names:
            params = params_base | {
                "typeName": type_name, 
                "typeNames": type_name, 
                "cql_filter": full_cql_filter
            }
            try:
                logger.debug(f"[GURS] WFS Poizvedba: URL={GURS_WFS_URL}, Params={params}")
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
                    continue
                
                response.raise_for_status()
                data = response.json()
                features = data.get("features", [])
                
                if features:
                    logger.info(f"[GURS] Najdenih {len(features)} parcel prek WFS (Type={type_name}, Filter={full_cql_filter})")
                    # Filtriramo naknadno po KO, če je bila podana
                    if ko_hint:
                        ko_lower = ko_hint.lower()
                        filtered_features = [
                            f for f in features 
                            if ko_lower in (f.get("properties", {}).get("IME_KO", "") or "").lower()
                        ]
                        if filtered_features: 
                            logger.info(f"Od tega se {len(filtered_features)} ujema s KO '{ko_hint}'.")
                            return filtered_features
                        else: 
                            logger.warning(f"Najdene parcele {parcel_no_clean}, a nobena ne ustreza KO '{ko_hint}'. Vračam vse.")
                            return features
                    else: 
                        return features
                else: 
                    logger.debug(f"[GURS] WFS OK, 0 zadetkov (Type={type_name}, Filter={full_cql_filter})")
                    
            except httpx.HTTPStatusError as exc: 
                logger.warning(f"[GURS] WFS HTTPStatusError {exc.response.status_code} (Type={type_name}, Filter={full_cql_filter}): {exc.response.text[:500]}")
            except Exception as exc: 
                logger.error(f"[GURS] WFS Splošna napaka (Type={type_name}, Filter={full_cql_filter}): {exc}", exc_info=True)
            continue

    logger.warning(f"[GURS] WFS poizvedba ni vrnila rezultatov za filter: {full_cql_filter}")
    return []
# === KONEC POPRAVLJENE FUNKCIJE ===

def _build_parcel_payload(feature: Dict[str, Any]) -> Dict[str, Any]:
    props = feature.get("properties") or {}; geometry = feature.get("geometry") or {}
    # Zdaj vemo, da WFS vrača ST_PARCE in IME_KO
    parcel_no = props.get("ST_PARCE") or "Neznano" 
    ko_name = props.get("IME_KO") or "Ni podatka"
    povrsina = props.get("POVRSINA") or props.get("RAC_POVRSINA") or 0
    namenska_raba = "Ni podatka (iz KN)" # To pride iz GetFeatureInfo klica
    center = _geometry_centroid(geometry)
    cache_key = _parcel_cache_key(parcel_no, ko_name)
    if not center: logger.warning(f"Ni centra za {parcel_no}, mock."); center = get_mock_coordinates(cache_key) 
    PARCEL_COORD_CACHE[cache_key] = center
    return {"stevilka": parcel_no, "katastrska_obcina": ko_name, "povrsina": int(povrsina) if povrsina else 0, "namenska_raba": namenska_raba, "coordinates": center}

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
    ko_safe = (ko or "unknown").strip().lower(); parcel_safe = (parcel_no or "unknown").strip(); return f"{parcel_safe}::{ko_safe}"

async def _resolve_parcel_coordinates(parcel_no: str, ko_hint: Optional[str]) -> List[float]:
    if not parcel_no: logger.warning("Pridobivam koordinate brez št. parcele."); return get_mock_coordinates(f"unknown-{ko_hint or ''}")
    cache_key = _parcel_cache_key(parcel_no, ko_hint)
    if cache_key in PARCEL_COORD_CACHE: logger.debug(f"Koordinate za '{cache_key}' iz cache."); return PARCEL_COORD_CACHE[cache_key]
    coords: Optional[List[float]] = None
    if ENABLE_REAL_GURS_API:
        logger.debug(f"Iščem koordinate za '{cache_key}' preko WFS...")
        features = await _fetch_parcel_features(parcel_no, ko_hint) # Uporabi novo funkcijo
        if features:
            payload = _build_parcel_payload(features[0]); coords = payload.get("coordinates")
            if coords: logger.info(f"Koordinate za '{cache_key}' iz WFS.")
            else: logger.warning(f"WFS vrnil parcelo za '{cache_key}', a centroid ni izračunan.")
        else: logger.warning(f"WFS ni našel parcele za '{cache_key}'.")
    if not coords: logger.debug(f"Uporabljam mock koordinate za '{cache_key}'."); coords = get_mock_coordinates(cache_key)
    PARCEL_COORD_CACHE[cache_key] = coords
    return coords