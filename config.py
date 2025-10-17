# app/config.py

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

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

DATABASE_URL = os.environ.get("DATABASE_URL")
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "local_sessions.db"

# Pot za začasno shranjevanje slik, ustvarjenih med sejami
TEMP_STORAGE_PATH = DATA_DIR / "temp_sessions"
TEMP_STORAGE_PATH.mkdir(exist_ok=True)


__all__ = [
    "API_KEY",
    "FAST_MODEL_NAME",
    "POWERFUL_MODEL_NAME",
    "GEN_CFG",
    "DATABASE_URL",
    "DEFAULT_SQLITE_PATH",
    "DATA_DIR",
    "TEMP_STORAGE_PATH",
]