# app/logging_config.py

from __future__ import annotations

import logging
import sys
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging():
    """
    Konfigurira napredno beleženje za aplikacijo.

    Nastavi:
    - Console handler za stdout (človeku berljiv format)
    - Rotating file handler za produkcijske loge (JSON format)
    - Različne nivoje za različne module
    """
    # Ustvarimo logs direktorij, če ne obstaja
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # Določimo nivo logiranja iz okoljske spremenljivke
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Odstranimo obstoječe handlerje (če obstajajo)
    root_logger.handlers.clear()

    # === CONSOLE HANDLER (človeku berljiv format) ===
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)-20s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # === FILE HANDLER (JSON format za produkcijo) ===
    log_file = logs_dir / os.getenv("LOG_FILE", "app.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        fmt='{"time":"%(asctime)s","level":"%(levelname)s","module":"%(name)s",'
            '"function":"%(funcName)s","line":%(lineno)d,"message":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # === NIVO LOGIRANJA ZA POSAMEZNE MODULE ===
    # Zmanjšamo "hrup" nekaterih knjižnic
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)

    # Aplikacijski moduli
    logging.getLogger("app").setLevel(numeric_level)

    logging.info(f"Logiranje nastavljeno: nivo={log_level}, datoteka={log_file}")