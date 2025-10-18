"""Frontend HTML helper."""
from __future__ import annotations

import json
from datetime import datetime

from pathlib import Path

from .config import FRONTEND_DIST_DIR, PROJECT_ROOT
from .municipalities import (
    get_default_municipality_slug,
    municipality_public_payload,
)

DEV_FRONTEND_PATH = PROJECT_ROOT / "frontend" / "index.html"


def _resolve_frontend_template() -> Path:
    dist_index = FRONTEND_DIST_DIR / "index.html"
    if dist_index.exists():
        return dist_index
    return DEV_FRONTEND_PATH


def build_homepage() -> str:
    template_path = _resolve_frontend_template()
    html = template_path.read_text(encoding="utf-8")
    html = html.replace("YEAR_PLACEHOLDER", str(datetime.now().year))
    html = html.replace(
        "DEFAULT_MUNICIPALITY_SLUG_PLACEHOLDER",
        get_default_municipality_slug(),
    )
    html = html.replace(
        "MUNICIPALITIES_JSON_PLACEHOLDER",
        json.dumps(municipality_public_payload(), ensure_ascii=False),
    )
    return html


__all__ = ["build_homepage"]
