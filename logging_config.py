# app/logging_config.py (NOVA DATOTEKA)

import logging
import sys

def setup_logging():
    """Konfigurira osnovno beleženje za aplikacijo."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout, # Logi se bodo izpisovali v terminal
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Zmanjšamo "hrup" nekaterih knjižnic
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)