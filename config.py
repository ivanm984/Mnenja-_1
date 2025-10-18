# app/config.py

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

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
    # Povečali smo maksimalno število izhodnih žetonov
    "max_output_tokens": int(os.environ.get("GEMINI_MAX_TOKENS", 40000)),
    "response_mime_type": "application/json",
}

GEMINI_ANALYSIS_CONCURRENCY = max(
    1, int(os.environ.get("GEMINI_ANALYSIS_CONCURRENCY", 3))
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL manjka v .env datoteki!")

DEFAULT_MUNICIPALITY_SLUG = os.environ.get("KNOWLEDGE_DEFAULT_MUNICIPALITY", "privzeta-obcina")
DEFAULT_MUNICIPALITY_NAME = os.environ.get("KNOWLEDGE_DEFAULT_MUNICIPALITY_NAME", "Privzeta občina")
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "local_sessions.db"

# Pot za začasno shranjevanje slik, ustvarjenih med sejami
TEMP_STORAGE_PATH = DATA_DIR / "temp_sessions"
TEMP_STORAGE_PATH.mkdir(exist_ok=True)


__all__ = [
    "API_KEY",
    "FAST_MODEL_NAME",
    "POWERFUL_MODEL_NAME",
    "GEN_CFG",
    "GEMINI_ANALYSIS_CONCURRENCY",
    "DATABASE_URL",
    "DEFAULT_MUNICIPALITY_SLUG",
    "DEFAULT_MUNICIPALITY_NAME",
    "DEFAULT_SQLITE_PATH",
    "DATA_DIR",
    "TEMP_STORAGE_PATH",
    "FRONTEND_DIST_DIR",
]