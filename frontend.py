"""Frontend HTML helper."""
from __future__ import annotations

import json
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Iterable

from .config import PROJECT_ROOT
from .municipalities import (
    get_default_municipality_slug,
    municipality_public_payload,
)

# Posodobljena različica uporabniškega vmesnika je shranjena kot
# ``modern_frontend.html`` v korenu paketa. Ob prvem zagonu v nekaterih
# okoljih (npr. ko je paket nameščen kot zip arhiv) neposreden dostop prek
# ``Path`` ne uspe, zato najprej poskusimo uporabiti ``importlib.resources``
# in šele nato lokalno pot kot rezervno možnost.
FRONTEND_FILENAME = "modern_frontend.html"
FRONTEND_PATH = PROJECT_ROOT / FRONTEND_FILENAME


def _template_candidates() -> Iterable[Path]:
    """Yield possible filesystem paths to the modern frontend template."""

    package = __package__ or "app"
    try:
        # ``importlib.resources.files`` poskrbi, da deluje tudi pri zgoščenih
        # distribucijah, kjer datoteka ni neposredno prisotna na datotečnem
        # sistemu. ``as_file`` poskrbi za morebitno razpakiranje v začasno
        # mapo.
        with resources.as_file(resources.files(package).joinpath(FRONTEND_FILENAME)) as handle:
            yield handle
    except (FileNotFoundError, ModuleNotFoundError):
        pass

    yield FRONTEND_PATH


_TEMPLATE_CACHE: str | None = None


def _load_template_text() -> str:
    """Read and cache the frontend HTML template contents."""

    global _TEMPLATE_CACHE

    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE

    for candidate in _template_candidates():
        try:
            _TEMPLATE_CACHE = candidate.read_text(encoding="utf-8")
            return _TEMPLATE_CACHE
        except FileNotFoundError:
            continue

    raise FileNotFoundError(
        "Posodobljene HTML predloge ni mogoče najti. Pričakovana je pod imenom "
        f"{FRONTEND_FILENAME}."
    )


def build_homepage() -> str:
    html = _load_template_text()
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
