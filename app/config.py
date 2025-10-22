# app/config.py
# PONOVNA VERZIJA (Onemogočeni problematični WMS sloji, preverjena sintaksa)

from __future__ import annotations
import hashlib
import os
from pathlib import Path
from urllib.parse import quote
from dotenv import load_dotenv
import warnings # Dodano za opozorila

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ==========================================
# GEMINI API NASTAVITVE
# ==========================================

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY manjka v .env datoteki!")

FAST_MODEL_NAME = os.environ.get("GEMINI_FAST_MODEL", "gemini-1.5-flash")
POWERFUL_MODEL_NAME = os.environ.get("GEMINI_POWERFUL_MODEL", "gemini-1.5-pro")

GEN_CFG = {
    "temperature": float(os.environ.get("GEMINI_TEMPERATURE", 0.0)),
    "top_p": float(os.environ.get("GEMINI_TOP_P", 0.9)),
    "top_k": int(os.environ.get("GEMINI_TOP_K", 40)),
    "max_output_tokens": int(os.environ.get("GEMINI_MAX_TOKENS", 8192)),
    "response_mime_type": "application/json",
}

GEMINI_ANALYSIS_CONCURRENCY = max(
    1, int(os.environ.get("GEMINI_ANALYSIS_CONCURRENCY", 3))
)

# ==========================================
# DATABASE NASTAVITVE
# ==========================================

DATABASE_URL = os.environ.get("DATABASE_URL")
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "local_sessions.db" # Ostane za referenco

if not DATABASE_URL:
    DEFAULT_SQLITE_PATH_STR = str(DEFAULT_SQLITE_PATH)
    DATABASE_URL = f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH_STR}"
    print(f"⚠️ OPOZORILO: DATABASE_URL ni nastavljen v .env. Uporabljam SQLite: {DATABASE_URL}")


# ==========================================
# SECURITY NASTAVITVE
# ==========================================

API_KEYS_RAW = os.environ.get("API_KEYS", "")


def hash_api_key(key: str) -> str:
    """Vrnemo SHA-256 hash API ključa."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


VALID_API_KEY_HASHES = {
    hash_api_key(key.strip())
    for key in API_KEYS_RAW.split(",")
    if key.strip()
}

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

if not VALID_API_KEY_HASHES and not DEBUG:
    raise RuntimeError("❌ API_KEYS manjka v .env datoteki! Potrebno za produkcijsko okolje.")
elif not VALID_API_KEY_HASHES and DEBUG:
    print("⚠️ OPOZORILO: API_KEYS ni nastavljen v .env. V DEBUG načinu dostop ni omejen.")

ALLOWED_ORIGINS_RAW = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]

RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))

# ==========================================
# REDIS NASTAVITVE
# ==========================================

REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
REDIS_USERNAME = os.environ.get("REDIS_USERNAME")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_DB = os.environ.get("REDIS_DB", "0")

if "REDIS_URL" in os.environ:
    REDIS_URL = os.environ["REDIS_URL"]
else:
    if not REDIS_PASSWORD and not DEBUG:
        raise RuntimeError(
            "❌ Redis povezava zahteva geslo. Nastavite REDIS_PASSWORD ali REDIS_URL."
        )
    if not REDIS_PASSWORD and DEBUG:
        print(
            "⚠️ OPOZORILO: REDIS_PASSWORD ni nastavljen. V DEBUG načinu je dovoljena nezaščitena povezava."
        )
    auth_part = ""
    if REDIS_PASSWORD:
        user_part = f"{REDIS_USERNAME}:" if REDIS_USERNAME else ""
        auth_part = f"{user_part}{quote(REDIS_PASSWORD)}@"
    REDIS_URL = f"redis://{auth_part}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "7200"))

# ==========================================
# FILE PROCESSING NASTAVITVE
# ==========================================

MAX_PDF_SIZE_MB = int(os.environ.get("MAX_PDF_SIZE_MB", "100"))
MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024
ANALYSIS_CHUNK_SIZE = int(os.environ.get("ANALYSIS_CHUNK_SIZE", "20"))

# ==========================================
# MUNICIPALITY NASTAVITVE
# ==========================================

DEFAULT_MUNICIPALITY_SLUG = os.environ.get("KNOWLEDGE_DEFAULT_MUNICIPALITY", "privzeta-obcina")
DEFAULT_MUNICIPALITY_NAME = os.environ.get("KNOWLEDGE_DEFAULT_MUNICIPALITY_NAME", "Privzeta občina")

# ==========================================
# TEMP STORAGE
# ==========================================

TEMP_STORAGE_PATH = DATA_DIR / "temp_sessions"
TEMP_STORAGE_PATH.mkdir(exist_ok=True)

# ==========================================
# GURS API NASTAVITVE
# ==========================================

GURS_API_KEY = os.getenv("GURS_API_KEY", None)

GURS_WMS_URL = os.getenv(
    "GURS_WMS_URL",
    "https://ipi.eprostor.gov.si/wms-si-gurs-kn/wms"
)

GURS_RASTER_WMS_URL = os.getenv(
    "GURS_RASTER_WMS_URL",
    "https://ipi.eprostor.gov.si/wms-si-gurs-dts/wms"
)

GURS_WFS_URL = os.getenv(
    "GURS_WFS_URL",
    "https://ipi.eprostor.gov.si/wfs-si-gurs-kn-osnovni/wfs"
)

GURS_RPE_WMS_URL = os.getenv(
    "GURS_RPE_WMS_URL",
    "https://ipi.eprostor.gov.si/wms-si-gurs-rpe/wms"
)

GURS_GEOCODE_URL = os.getenv(
    "GURS_GEOCODE_URL",
    "https://storitve.eprostor.gov.si/kn/api"
)

GURS_API_TIMEOUT = float(os.getenv("GURS_API_TIMEOUT", "30.0"))

# ==========================================
# ZEMLJEVID NASTAVITVE
# ==========================================

DEFAULT_MAP_CENTER = (
    float(os.getenv("DEFAULT_MAP_CENTER_LON", "14.8267")),
    float(os.getenv("DEFAULT_MAP_CENTER_LAT", "46.0569"))
)
DEFAULT_MAP_ZOOM = int(os.getenv("DEFAULT_MAP_ZOOM", "14"))

# ==========================================
# FEATURE FLAGS
# ==========================================

ENABLE_GURS_MAP = os.getenv("ENABLE_GURS_MAP", "true").lower() == "true"
ENABLE_REAL_GURS_API = os.getenv("ENABLE_REAL_GURS_API", "true").lower() == "true"
# DEBUG flag je definiran zgoraj

# ==========================================
# GURS WMS SLOJI
# ==========================================

GURS_WMS_LAYERS = {
    "ortofoto": {
        "name": "SI.GURS.ZPDZ:DOF025",
        "title": "Digitalni ortofoto",
        "description": "Ortofoto posnetek Slovenije",
        "url": GURS_RASTER_WMS_URL,
        "format": "image/jpeg",
        "transparent": False,
        "category": "base",
        "default_visible": True
    },
    "katastr": {
        "name": "SI.GURS.KN:PARCELE",
        "title": "Parcelne meje",
        "description": "Meje parcel iz katastra nepremičnin",
        "url": GURS_WMS_URL,
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": True,
        "always_on": True
    },
    "katastr_stevilke": {
        "title": "Parcelne številke",
        "description": "Prikaz številk parcel iz katastra",
        "url": GURS_WMS_URL,
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": True,
        "always_on": False,
        "name_candidates": [
            "SI.GURS.KN:PARCELNE_STEVILKE",
            "SI.GURS.KN:PARCELNE_CENTROID"
        ],
        "title_keywords": ["parcel", "številk"]
    },
    "namenska_raba": {
        "name": "RPE:RPE_PO", # ✅ POPRAVLJENO: Uporaba RPE strežnika
        "title": "Namenska raba (RPE)",
        "description": "Namenska raba prostora iz registra prostorskih enot",
        "url": GURS_RPE_WMS_URL, # ✅ POPRAVLJENO: Uporaba RPE strežnika
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": False, # Izklopljeno privzeto, uporabnik vklopi po potrebi
        "opacity": 0.6
    },
    "stavbe": {
        "name": "SI.GURS.KN:STAVBE", # To ime je verjetno pravilno
        "title": "Stavbni kataster",
        "description": "Stavbe iz katastra nepremičnin",
        "url": GURS_WMS_URL,
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": False # Pustimo izklopljeno za zdaj
    },
    "hisne_stevilke": {
        "title": "Hišne številke",
        "description": "Prikaz hišnih številk",
        "url": GURS_WMS_URL,
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": False,
        "name_candidates": [
            "SI.GURS.KN:HS_STEVILKE",
            "SI.GURS.KN:HISNE_STEVILKE",
            "SI.GURS.KN:HS"
        ],
        "title_keywords": ["hišn", "števil"]
    },
    # --- Ostali sloji zakomentirani ---
    # "dtm": {
    #     "name": "DTM",
    #     "title": "Digitalni model terena",
    #     "url": GURS_RASTER_WMS_URL,
    #     "format": "image/png",
    #     "transparent": True,
    #     "category": "overlay",
    #     "default_visible": False
    # },
    # "poplavna": {
    #     "name": "POP",
    #     "title": "Poplavna območja",
    #     "url": GURS_WMS_URL,
    #     "format": "image/png",
    #     "transparent": True,
    #     "category": "overlay",
    #     "default_visible": False
    # }
}

# ==========================================
# VALIDATION
# ==========================================

def validate_gurs_config():
    """Preveri, če so GURS nastavitve pravilne."""
    if ENABLE_REAL_GURS_API and not GURS_API_KEY:
        warnings.warn(
            "ENABLE_REAL_GURS_API=true ampak GURS_API_KEY ni nastavljen! "
            "Za dostop do *zasebnih* GURS APIjev je potreben ključ."
        )
    if DEBUG:
        print("--- GURS Configuration ---")
        print(f"Zemljevid omogočen: {'Da' if ENABLE_GURS_MAP else 'Ne'}")
        print(f"Uporaba pravih GURS APIjev: {'Da' if ENABLE_REAL_GURS_API else 'Ne (simulacija)'}")
        print(f"Privzeti center zemljevida: {DEFAULT_MAP_CENTER}")
        print(f"Privzeti zoom zemljevida: {DEFAULT_MAP_ZOOM}")
        print(f"KN WMS URL: {GURS_WMS_URL}")
        print(f"DTS WMS URL (Ortofoto): {GURS_RASTER_WMS_URL}")
        print(f"RPE WMS URL (Nam. raba): {GURS_RPE_WMS_URL}")
        print(f"KN WFS URL (Podatki): {GURS_WFS_URL}")
        print(f"Geokodiranje URL: {GURS_GEOCODE_URL}")
        print(f"API Timeout: {GURS_API_TIMEOUT}s")
        print("--- Configured WMS Layers ---")
        for layer_id, cfg in GURS_WMS_LAYERS.items():
            print(f"- ID: {layer_id}, Name: {cfg.get('name')}, Title: {cfg.get('title')}, URL: {cfg.get('url')}, Visible: {cfg.get('default_visible')}")
        print("---------------------------")


if ENABLE_GURS_MAP:
    validate_gurs_config()

# ==========================================
# EXPORTS
# ==========================================

__all__ = [
    "API_KEY", "FAST_MODEL_NAME", "POWERFUL_MODEL_NAME", "GEN_CFG", "GEMINI_ANALYSIS_CONCURRENCY",
    "DATABASE_URL", "DEFAULT_SQLITE_PATH",
    "DEFAULT_MUNICIPALITY_SLUG", "DEFAULT_MUNICIPALITY_NAME",
    "PROJECT_ROOT", "DATA_DIR", "TEMP_STORAGE_PATH",
    "GURS_API_KEY", "GURS_WMS_URL", "GURS_RASTER_WMS_URL", "GURS_RPE_WMS_URL",
    "GURS_WFS_URL", "GURS_GEOCODE_URL", "GURS_API_TIMEOUT",
    "DEFAULT_MAP_CENTER", "DEFAULT_MAP_ZOOM",
    "ENABLE_GURS_MAP", "ENABLE_REAL_GURS_API", "GURS_WMS_LAYERS", "DEBUG",
    "hash_api_key", "VALID_API_KEY_HASHES", "ALLOWED_ORIGINS", "RATE_LIMIT_PER_MINUTE",
    "REDIS_URL", "SESSION_TTL_SECONDS",
    "MAX_PDF_SIZE_MB", "MAX_PDF_SIZE_BYTES", "ANALYSIS_CHUNK_SIZE",
]
