from __future__ import annotations
from datetime import datetime
from .config import PROJECT_ROOT

MODERN_FRONTEND_PATH = PROJECT_ROOT / "app" / "modern_frontend.html"

def build_homepage() -> str:
    html = MODERN_FRONTEND_PATH.read_text(encoding="utf-8")
    html = html.replace("YEAR_PLACEHOLDER", str(datetime.now().year))
    return html

__all__ = ["build_homepage"]