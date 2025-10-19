"""Frontend HTML helper."""
from __future__ import annotations

import json
from datetime import datetime

from .config import PROJECT_ROOT
from .municipalities import (
    get_default_municipality_slug,
    municipality_public_payload,
)

# Posodobljena različica uporabniškega vmesnika je shranjena kot
# ``modern_frontend.html`` v korenu paketa. Prejšnja nastavitev je še vedno
# iskala neobstoječo pot ``app/frontend.html``, zaradi česar se je ob prvem
# obisku vrnila napaka oziroma prazna stran. Usmerimo referenco na dejansko
# datoteko.
FRONTEND_PATH = PROJECT_ROOT / "modern_frontend.html"


def build_homepage() -> str:
    html = FRONTEND_PATH.read_text(encoding="utf-8")
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
