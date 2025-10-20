# app/gurs_routes.py
# POSODOBLJENA VERZIJA

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from .cache import cache_manager
from .config import PROJECT_ROOT

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gurs", tags=["GURS"])

# Pot do HTML datoteke za zemljevid
GURS_MAP_HTML = PROJECT_ROOT / "app" / "gurs_map.html"


@router.get("/map", response_class=HTMLResponse)
async def gurs_map_page():
    """Prikaži GURS zemljevid stran."""
    if not GURS_MAP_HTML.exists():
        raise HTTPException(status_code=404, detail="GURS zemljevid ni na voljo")
    
    return GURS_MAP_HTML.read_text(encoding="utf-8")


@router.get("/search-parcel")
async def search_parcel(query: str = Query(..., description="Parcela številka (npr. 123/5)")):
    """Išči parcelo po številki."""
    logger.info(f"[GURS] Iskanje parcele: {query}")
    
    query_clean = query.strip()
    
    # Za demo - simulirani podatki
    mock_parcel = {
        "stevilka": query_clean,
        "katastrska_obcina": "Litija",
        "coordinates": get_mock_coordinates(query_clean),
        "povrsina": abs(hash(query_clean) % 2000) + 500,
        "namenska_raba": "SSe - Površine podeželskega naselja"
    }
    
    return {
        "success": True,
        "parcels": [mock_parcel]
    }


@router.get("/session-parcels/{session_id}")
async def get_session_parcels(session_id: str):
    """Pridobi parcele iz AI ekstrakcije za določeno sejo."""
    logger.info(f"[GURS] Pridobivam parcele za sejo: {session_id}")
    
    # Pridobi podatke iz cache
    data = await cache_manager.retrieve_session_data(session_id)
    
    if not data:
        raise HTTPException(status_code=404, detail="Seja ne obstaja ali je potekla")
    
    # Ekstrahiraj podatke o parcelah
    parcels = extract_parcels_from_session(data)
    
    logger.info(f"[GURS] Ekstrahiranih {len(parcels)} parcel")
    
    if not parcels:
        return {
            "success": True,
            "parcels": [],
            "message": "Ni najdenih parcel v projektu"
        }
    
    # Dodaj koordinate
    parcels_with_coords = []
    for parcel in parcels:
        coords = get_mock_coordinates(parcel["stevilka"])
        parcel["coordinates"] = coords
        parcels_with_coords.append(parcel)
        logger.info(f"[GURS] Parcela {parcel['stevilka']}: {coords}")
    
    return {
        "success": True,
        "parcels": parcels_with_coords
    }


def extract_parcels_from_session(session_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Ekstrahiraj podatke o parcelah iz session podatkov."""
    parcels = []
    
    # Pridobi podatke
    key_data = session_data.get("key_data", {})
    
    logger.info(f"[GURS] === EKSTRAHIRAM PARCELE ===")
    logger.info(f"[GURS] Key data keys: {list(key_data.keys())}")
    
    # Gradbena parcela
    gradbena_parcela = key_data.get("parcela_objekta", "")
    logger.info(f"[GURS] Gradbena parcela: '{gradbena_parcela}'")
    
    # Vse parcele in K.O.
    vse_parcele = key_data.get("stevilke_parcel_ko", "")
    logger.info(f"[GURS] Vse parcele raw: '{vse_parcele}'")
    
    velikost_str = key_data.get("velikost_parcel", "")
    logger.info(f"[GURS] Velikost: '{velikost_str}'")
    
    # Katastrska občina
    ko_match = re.search(r"k\.o\.\s*(\w+)", vse_parcele, re.IGNORECASE)
    katastrska_obcina = ko_match.group(1) if ko_match else "Litija"
    logger.info(f"[GURS] Katastrska občina: '{katastrska_obcina}'")
    
    # Namenska raba
    ai_details = session_data.get("ai_details", {})
    namenska_raba_list = ai_details.get("namenska_raba", [])
    namenska_raba = namenska_raba_list[0] if namenska_raba_list else "Ni podatka"
    logger.info(f"[GURS] Namenska raba: '{namenska_raba}'")
    
    # Parse velikost
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
    
    # Ekstrahiraj parcele
    if vse_parcele and vse_parcele.strip():
        # Odstrani K.O. del
        parcele_str = re.sub(r"k\.o\..*", "", vse_parcele, flags=re.IGNORECASE)
        logger.info(f"[GURS] Parcele brez K.O.: '{parcele_str}'")
        
        # Razdeli po vejicah, podpičjih, ali newline
        parcela_numbers = []
        for p in re.split(r'[,;\n]', parcele_str):
            p_clean = p.strip()
            if p_clean and p_clean.lower() != 'k.o.' and len(p_clean) > 0:
                parcela_numbers.append(p_clean)
        
        logger.info(f"[GURS] Najdene parcele: {parcela_numbers}")
        
        if parcela_numbers:
            povrsina_per_parcel = velikost_int // len(parcela_numbers)
            
            for parcela_num in parcela_numbers:
                parcels.append({
                    "stevilka": parcela_num,
                    "katastrska_obcina": katastrska_obcina,
                    "povrsina": povrsina_per_parcel,
                    "namenska_raba": namenska_raba
                })
    
    # Če ni parcel, uporabi gradbeno parcelo
    if not parcels and gradbena_parcela and gradbena_parcela.strip():
        logger.info(f"[GURS] Uporabljam gradbeno parcelo: '{gradbena_parcela}'")
        parcels.append({
            "stevilka": gradbena_parcela.strip(),
            "katastrska_obcina": katastrska_obcina,
            "povrsina": velikost_int,
            "namenska_raba": namenska_raba
        })
    
    logger.info(f"[GURS] === REZULTAT: {len(parcels)} parcel ===")
    for i, p in enumerate(parcels, 1):
        logger.info(f"[GURS] Parcela {i}: {p['stevilka']} ({p['katastrska_obcina']})")
    
    return parcels


def get_mock_coordinates(parcela: str) -> List[float]:
    """
    Generiraj konsistentne simulirane koordinate za parcelo.
    Center: Litija [14.8267, 46.0569]
    Radius: ~1km
    """
    # Base koordinate - CENTER LITIJA (NE Ljubljana!)
    base_lon = 14.8267
    base_lat = 46.0569
    
    # Hash za konsistentnost
    hash_val = abs(hash(parcela))
    
    # Offset v radiusu ~1000m
    offset_lon = ((hash_val % 2000) - 1000) * 0.00001
    offset_lat = (((hash_val // 2000) % 2000) - 1000) * 0.00001
    
    lon = base_lon + offset_lon
    lat = base_lat + offset_lat
    
    logger.info(f"[GURS] Koordinate za '{parcela}': [{lon:.6f}, {lat:.6f}]")
    
    return [lon, lat]


@router.get("/parcel-info/{parcela_st}")
async def get_parcel_info(
    parcela_st: str,
    ko: Optional[str] = Query(None, description="Katastrska občina")
):
    """Pridobi podrobne informacije o parceli."""
    logger.info(f"[GURS] Info za parcelo: {parcela_st}, K.O.: {ko}")
    
    return {
        "success": True,
        "parcel": {
            "stevilka": parcela_st,
            "katastrska_obcina": ko or "Litija",
            "povrsina": abs(hash(parcela_st) % 2000) + 500,
            "namenska_raba": "SSe - Površine podeželskega naselja",
            "lastniki": "Zaščiteni podatki",
            "obremenjenja": "Ni"
        }
    }


@router.get("/wms-capabilities")
async def get_wms_capabilities():
    """Vrni informacije o dostopnih GURS WMS slojih."""
    return {
        "success": True,
        "layers": [
            {
                "name": "DOF",
                "title": "Digitalni ortofoto",
                "description": "Ortofoto posnetek Slovenije"
            },
            {
                "name": "KN_ZK",
                "title": "Zemljiški kataster",
                "description": "Parcelne meje in številke"
            },
            {
                "name": "KN_SN",
                "title": "Stavbni kataster",
                "description": "Stavbe in objekti"
            },
            {
                "name": "OPN_RABA",
                "title": "Namenska raba",
                "description": "Prostorski načrt - namenska raba"
            },
            {
                "name": "DTM",
                "title": "Digitalni model terena",
                "description": "Višinski podatki"
            },
            {
                "name": "POP",
                "title": "Poplavna območja",
                "description": "Območja ogrožena s poplavami"
            }
        ],
        "wms_url": "https://prostor.gov.si/wms"
    }