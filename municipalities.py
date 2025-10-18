"""Configuration of supported municipalities and their specific defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .config import DEFAULT_MUNICIPALITY_NAME, DEFAULT_MUNICIPALITY_SLUG


@dataclass(frozen=True)
class MunicipalityProfile:
    """Static configuration for a single municipality."""

    slug: str
    name: str
    knowledge_slug: str
    email_domains: Set[str] = field(default_factory=set)
    default_metadata: Dict[str, str] = field(default_factory=dict)
    prompt_context: str = ""
    prompt_special_rules: List[str] = field(default_factory=list)


_LITIJA_LEGAL_BASIS = "\n".join(
    [
        "• 61. člen Gradbenega zakona GZ-1 (Uradni list RS, št. 199/21, 105/22 – ZZNŠPP in 132/23 – ZPNačrt)",
        "• 257. člen Zakona o urejanju prostora ZUreP-3 (Uradni list RS, št. 199/21)",
        "• Odlok o občinskem prostorskem načrtu Občine Litija (Uradni list RS, št. 113/15, 48/16 – popr., 199/21 – ZUreP-3)",
        "• Odlok o določitvi podrobnejše namenske rabe prostora v OPN Občine Litija (Uradni list RS, št. 48/16 – popr.)",
    ]
)


_MUNICIPALITIES: Dict[str, MunicipalityProfile] = {
    DEFAULT_MUNICIPALITY_SLUG: MunicipalityProfile(
        slug=DEFAULT_MUNICIPALITY_SLUG,
        name=DEFAULT_MUNICIPALITY_NAME,
        knowledge_slug=DEFAULT_MUNICIPALITY_SLUG,
        email_domains={"@litija.si", "@obcina-litija.si"},
        default_metadata={
            "mnenjedajalec": "OBČINA LITIJA",
            "mnenjedajalec_naziv": "OBČINA LITIJA",
            "mnenjedajalec_naslov": "Jerebova ulica 14, 1270 Litija",
            "postopek_vodil": "Tina Dragić, mag. inž. arh.",
            "odgovorna_oseba": "Tina Dragić, mag. inž. arh.",
            "izdelovalec_porocila": "Tina Dragić, mag. inž. arh.",
            "predpisi": _LITIJA_LEGAL_BASIS,
            "stevilka_porocila": "",
        },
        prompt_context=(
            "Vsi podatki o prostorskih aktih se nanašajo na Občino Litija. "
            "Uporabi katalog OPN Občine Litija in njegove priloge kot izvor zahtev."
        ),
        prompt_special_rules=[
            "Če se v dokumentaciji pojavi navedba OPN ali njegovih prilog, predpostavi, da gre za OPN Občine Litija.",
            "Odlok o določitvi podrobnejše namenske rabe prostora (Uradni list RS, št. 48/16 – popr.) je primarni vir za posebne pogoje.",
            "Uredba o razvrščanju objektov je državna in velja za vse občine; združi jo z lokalnimi pravili Občine Litija.",
        ],
    )
}


def list_municipality_profiles() -> List[MunicipalityProfile]:
    """Return all configured municipality profiles."""

    return list(_MUNICIPALITIES.values())


def get_default_municipality_slug() -> str:
    """Return the slug of the default municipality."""

    return DEFAULT_MUNICIPALITY_SLUG


def get_municipality_profile(identifier: Optional[str] = None) -> MunicipalityProfile:
    """Return the profile for *identifier* or the default profile."""

    if identifier:
        slug = identifier.strip().lower()
        if "@" in slug:
            matched = match_municipality_by_email(slug)
            if matched:
                return matched
        if slug in _MUNICIPALITIES:
            return _MUNICIPALITIES[slug]
    return _MUNICIPALITIES[DEFAULT_MUNICIPALITY_SLUG]


def match_municipality_by_email(email: str) -> Optional[MunicipalityProfile]:
    """Match a municipality profile based on *email* domain."""

    normalized = email.strip().lower()
    at_index = normalized.rfind("@")
    if at_index == -1:
        return None
    domain = normalized[at_index:]
    for profile in _MUNICIPALITIES.values():
        for candidate in profile.email_domains:
            if domain.endswith(candidate.lower()):
                return profile
    return None


def municipality_public_payload() -> List[Dict[str, Any]]:
    """Return serialisable data used by the frontend."""

    payload: List[Dict[str, Any]] = []
    for profile in list_municipality_profiles():
        payload.append(
            {
                "slug": profile.slug,
                "name": profile.name,
                "default_metadata": profile.default_metadata,
                "prompt_context": profile.prompt_context,
                "prompt_special_rules": profile.prompt_special_rules,
            }
        )
    return payload


__all__ = [
    "MunicipalityProfile",
    "get_default_municipality_slug",
    "get_municipality_profile",
    "list_municipality_profiles",
    "match_municipality_by_email",
    "municipality_public_payload",
]

