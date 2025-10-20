# app/config.py
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

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

# Model za hitro ekstrakcijo podatkov (prvi korak)
FAST_MODEL_NAME = os.environ.get("GEMINI_FAST_MODEL", "gemini-2.5-flash")

# Model za kompleksno analizo skladnosti (drugi korak)
POWERFUL_MODEL_NAME = os.environ.get("GEMINI_POWERFUL_MODEL", "gemini-2.5-pro")

GEN_CFG = {
    "temperature": float(os.environ.get("GEMINI_TEMPERATURE", 0.0)),
    "top_p": float(os.environ.get("GEMINI_TOP_P", 0.9)),
    "top_k": int(os.environ.get("GEMINI_TOP_K", 40)),
    "max_output_tokens": int(os.environ.get("GEMINI_MAX_TOKENS", 40000)),
    "response_mime_type": "application/json",
}

GEMINI_ANALYSIS_CONCURRENCY = max(
    1, int(os.environ.get("GEMINI_ANALYSIS_CONCURRENCY", 3))
)

# ==========================================
# DATABASE NASTAVITVE
# ==========================================

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL manjka v .env datoteki!")

DEFAULT_SQLITE_PATH = PROJECT_ROOT / "local_sessions.db"

# ==========================================
# MUNICIPALITY NASTAVITVE
# ==========================================

DEFAULT_MUNICIPALITY_SLUG = os.environ.get("KNOWLEDGE_DEFAULT_MUNICIPALITY", "privzeta-obcina")
DEFAULT_MUNICIPALITY_NAME = os.environ.get("KNOWLEDGE_DEFAULT_MUNICIPALITY_NAME", "Privzeta občina")

# ==========================================
# TEMP STORAGE
# ==========================================

# Pot za začasno shranjevanje slik, ustvarjenih med sejami
TEMP_STORAGE_PATH = DATA_DIR / "temp_sessions"
TEMP_STORAGE_PATH.mkdir(exist_ok=True)

# ==========================================
# GURS API NASTAVITVE
# ==========================================

# GURS API ključ (opcijsko - za produkcijsko uporabo)
GURS_API_KEY = os.getenv("GURS_API_KEY", None)

# GURS URLs
GURS_WMS_URL = os.getenv(
    "GURS_WMS_URL", 
    "https://prostor3.gov.si/egp/services/javni/OGC_EPSG3857_RASTER/MapServer/WMSServer"
)

GURS_WFS_URL = os.getenv(
    "GURS_WFS_URL",
    "https://prostor3.gov.si/egp/services/javni/OGC_EPSG3857_VEKTORJI/MapServer/WFSServer"
)

# Timeout za GURS API klice
GURS_API_TIMEOUT = float(os.getenv("GURS_API_TIMEOUT", "30"))

# ==========================================
# ZEMLJEVID NASTAVITVE
# ==========================================

# Privzete koordinate (Litija)
DEFAULT_MAP_CENTER = (
    float(os.getenv("DEFAULT_MAP_CENTER_LON", "14.5058")),
    float(os.getenv("DEFAULT_MAP_CENTER_LAT", "46.0569"))
)

DEFAULT_MAP_ZOOM = int(os.getenv("DEFAULT_MAP_ZOOM", "14"))

# ==========================================
# FEATURE FLAGS
# ==========================================

# Ali je GURS zemljevid omogočen
ENABLE_GURS_MAP = os.getenv("ENABLE_GURS_MAP", "true").lower() == "true"

# Ali uporabljamo pravi GURS API ali simulirane podatke
ENABLE_REAL_GURS_API = os.getenv("ENABLE_REAL_GURS_API", "false").lower() == "true"

# Debug mode
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ==========================================
# GURS WMS SLOJI
# ==========================================

GURS_WMS_LAYERS = {
    "ortofoto": {
        "name": "DOF",
        "title": "Digitalni ortofoto",
        "description": "Ortofoto posnetek Slovenije"
    },
    "katastr": {
        "name": "KN_ZK",
        "title": "Katastrske meje",
        "description": "Parcelne meje in številke"
    },
    "namenska_raba": {
        "name": "OPN_RABA",
        "title": "Namenska raba",
        "description": "Prostorski načrt - namenska raba"
    },
    "dtm": {
        "name": "DTM",
        "title": "Digitalni model terena",
        "description": "Višinski podatki"
    }
}

# ==========================================
# VALIDATION
# ==========================================

def validate_gurs_config():
    """Preveri, če so GURS nastavitve pravilne."""
    
    if ENABLE_REAL_GURS_API and not GURS_API_KEY:
        import warnings
        warnings.warn(
            "ENABLE_REAL_GURS_API=true ampak GURS_API_KEY ni nastavljen! "
            "Pridobite API ključ na https://prostor.gov.si"
        )
    
    if DEBUG:
        print(f"[GURS Config] Zemljevid: {'Omogočen' if ENABLE_GURS_MAP else 'Onemogočen'}")
        print(f"[GURS Config] Pravi API: {'Da' if ENABLE_REAL_GURS_API else 'Ne (simulacija)'}")
        print(f"[GURS Config] Center: {DEFAULT_MAP_CENTER}")

# Pokliči validacijo ob importu
if ENABLE_GURS_MAP:
    validate_gurs_config()

# ==========================================
# EXPORTS
# ==========================================

__all__ = [
    # Gemini
    "API_KEY",
    "FAST_MODEL_NAME",
    "POWERFUL_MODEL_NAME",
    "GEN_CFG",
    "GEMINI_ANALYSIS_CONCURRENCY",
    
    # Database
    "DATABASE_URL",
    "DEFAULT_SQLITE_PATH",
    
    # Municipality
    "DEFAULT_MUNICIPALITY_SLUG",
    "DEFAULT_MUNICIPALITY_NAME",
    
    # Paths
    "PROJECT_ROOT",
    "DATA_DIR",
    "TEMP_STORAGE_PATH",
    
    # GURS
    "GURS_API_KEY",
    "GURS_WMS_URL",
    "GURS_GEOCODE_URL",
    "GURS_API_TIMEOUT",
    "DEFAULT_MAP_CENTER",
    "DEFAULT_MAP_ZOOM",
    "ENABLE_GURS_MAP",
    "ENABLE_REAL_GURS_API",
    "GURS_WMS_LAYERS",
    "DEBUG",
]