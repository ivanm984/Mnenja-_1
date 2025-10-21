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
# SECURITY NASTAVITVE
# ==========================================

# API Keys za avtentikacijo
API_KEYS_RAW = os.environ.get("API_KEYS", "")
VALID_API_KEYS = set(key.strip() for key in API_KEYS_RAW.split(",") if key.strip())

if not VALID_API_KEYS and not DEBUG:
    raise RuntimeError("❌ API_KEYS manjka v .env datoteki!")

# CORS nastavitve
ALLOWED_ORIGINS_RAW = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]

# Rate limiting
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))

# ==========================================
# REDIS NASTAVITVE
# ==========================================

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "3600"))

# ==========================================
# FILE PROCESSING NASTAVITVE
# ==========================================

MAX_PDF_SIZE_MB = int(os.environ.get("MAX_PDF_SIZE_MB", "50"))
MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024
ANALYSIS_CHUNK_SIZE = int(os.environ.get("ANALYSIS_CHUNK_SIZE", "15"))

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
    "https://ipi.eprostor.gov.si/wms-si-gurs-kn/wms"  # Kataster (KN) - za meje, št., stavbe, NEP_... sloje
)

GURS_RASTER_WMS_URL = os.getenv(
    "GURS_RASTER_WMS_URL",
    "https://ipi.eprostor.gov.si/wms-si-gurs-dts/wms" # Ortofoto (Digitalni Topo Sistem - DTS)
)

GURS_WFS_URL = os.getenv(
    "GURS_WFS_URL",
    "https://ipi.eprostor.gov.si/wfs-si-gurs-kn-osnovni/wfs"  # ✅ POPRAVLJEN: Kataster WFS (KN Osnovni)
)

# URL za namensko rabo (Register Prostorskih Enot - RPE) - Ohranimo za vsak slučaj, čeprav ga zdaj ne rabimo za privzeti sloj
GURS_RPE_WMS_URL = os.getenv(
    "GURS_RPE_WMS_URL",
    "https://ipi.eprostor.gov.si/wms-si-gurs-rpe/wms"
)

GURS_GEOCODE_URL = os.getenv(
    "GURS_GEOCODE_URL",
    "https://prostor.gov.si/ows" # To je OK, ker povozi .env z https://storitve.eprostor.gov.si/kn/api
)

# Timeout za GURS API klice
GURS_API_TIMEOUT = float(os.getenv("GURS_API_TIMEOUT", "30"))

# ==========================================
# ZEMLJEVID NASTAVITVE
# ==========================================

DEFAULT_MAP_CENTER = (
    float(os.getenv("DEFAULT_MAP_CENTER_LON", "14.5058")),
    float(os.getenv("DEFAULT_MAP_CENTER_LAT", "46.0569"))
)
DEFAULT_MAP_ZOOM = int(os.getenv("DEFAULT_MAP_ZOOM", "14"))

# ==========================================
# FEATURE FLAGS
# ==========================================

ENABLE_GURS_MAP = os.getenv("ENABLE_GURS_MAP", "true").lower() == "true"
ENABLE_REAL_GURS_API = os.getenv("ENABLE_REAL_GURS_API", "false").lower() == "true"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ==========================================
# GURS WMS SLOJI (POPRAVLJENO z NEP_ imeni)
# ==========================================

GURS_WMS_LAYERS = {
    "ortofoto": {
        "name": "SI.GURS.ZPDZ:DOF025",
        "title": "Digitalni ortofoto",
        "description": "Ortofoto posnetek Slovenije",
        "url": GURS_RASTER_WMS_URL, # Pravilen URL (.../wms-si-gurs-dts/wms)
        "format": "image/jpeg",
        "transparent": False,
        "category": "base", # Osnovni sloj
        "default_visible": True # Privzeto viden
    },
     "katastr": {
        "name": "SI.GURS.KN:PARCELE", # Osnovne meje parcel
        "title": "Parcelne meje",
        "description": "Meje parcel iz katastra nepremičnin",
        "url": GURS_WMS_URL, # Pravilen URL (.../wms-si-gurs-kn/wms)
        "format": "image/png",
        "transparent": True,
        "category": "overlay", # Dodatni sloj
        "default_visible": True, # Vedno viden
        "always_on": True # Ne da se ga izklopiti
    },
    "katastr_stevilke": {
        # OPOMBA: Številke parcel so lahko prikazane preko GetFeatureInfo
        # Nekateri strežniki imajo posebne sloje (NEP_OSNOVNI_PARCELE_CENTROID, SI.GURS.KN:PARCELNE_CENTROID)
        # Če ta sloj ne deluje, poskusite spremeniti ime ali uporabiti GetFeatureInfo na klik
        "name": "SI.GURS.KN:PARCELNE_CENTROID",  # Alternativa: NEP_OSNOVNI_PARCELE_CENTROID
        "title": "Številke parcel",
        "description": "Centroidi parcel s številkami (če sloj ne deluje, številke dobite s klikom na parcelo)",
        "url": GURS_WMS_URL,
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": False,  # Spremenjeno na False, ker sloj morda ne obstaja
        "always_on": False
    },
    "namenska_raba": {
        # OPOMBA: Namenska raba je običajno specifična za občino (OPN sloji)
        # Za splošno namensko rabo uporabite RPE strežnik
        # Ime sloja se lahko razlikuje (NEP_OST_NAMENSKE_RABE, OPN_*, RPE_*)
        "name": "RPE:RPE_PO",  # Register prostorskih enot - prostorski odseki
        "title": "Namenska raba (RPE)",
        "description": "Namenska raba prostora iz registra prostorskih enot",
        "url": GURS_RPE_WMS_URL,  # Uporabimo RPE strežnik
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": True,  # Spremenimo na True za testiranje
        "opacity": 0.6  # Dodamo prosojnost
    },
    "stavbe": {
        "name": "SI.GURS.KN:STAVBE", # Osnovni podatki o stavbah
        "title": "Stavbni kataster",
        "description": "Stavbe iz katastra nepremičnin",
        "url": GURS_WMS_URL, # Pravilen URL (.../wms-si-gurs-kn/wms)
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": False
    },
    # Primer dodatnega infrastrukturnega sloja (če ga najdete v katalogu)
    # "infrastruktura_elektro": {
    #     "name": "NEP_GJI_ELEKTRO", # IZMIŠLJENO IME - preverite v katalogu!
    #     "title": "Elektro omrežje",
    #     "description": "Podatki o elektroenergetskem omrežju",
    #     "url": GURS_WMS_URL, # Verjetno KN strežnik
    #     "format": "image/png",
    #     "transparent": True,
    #     "category": "overlay",
    #     "default_visible": False
    # },
    # --- Ostali sloji, ki morda ne delujejo ---
    "dtm": {
        "name": "DTM", # Verjetno napačno ime
        "title": "Digitalni model terena",
        "url": GURS_RASTER_WMS_URL,
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": False
    },
    "poplavna": {
        "name": "POP", # Verjetno napačno ime
        "title": "Poplavna območja",
        "url": GURS_WMS_URL, # Verjetno napačen URL/ime
        "format": "image/png",
        "transparent": True,
        "category": "overlay",
        "default_visible": False
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
            "Pridobite API ključ na https://www.e-prostor.gov.si/"
        )
    if DEBUG:
        print(f"[GURS Config] Zemljevid: {'Omogočen' if ENABLE_GURS_MAP else 'Onemogočen'}")
        print(f"[GURS Config] Pravi API: {'Da' if ENABLE_REAL_GURS_API else 'Ne (simulacija)'}")
        print(f"[GURS Config] Center: {DEFAULT_MAP_CENTER}")
        print(f"[GURS Config] KN WMS URL: {GURS_WMS_URL}")
        print(f"[GURS Config] DTS WMS URL: {GURS_RASTER_WMS_URL}")
        print(f"[GURS Config] RPE WMS URL: {GURS_RPE_WMS_URL}")
        print(f"[GURS Config] KN WFS URL: {GURS_WFS_URL}")

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
    "VALID_API_KEYS", "ALLOWED_ORIGINS", "RATE_LIMIT_PER_MINUTE",
    "REDIS_URL", "SESSION_TTL_SECONDS",
    "MAX_PDF_SIZE_MB", "MAX_PDF_SIZE_BYTES", "ANALYSIS_CHUNK_SIZE",
]