"""Loading and working with the local planning knowledge base."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Pattern, Tuple

from .knowledge_store import knowledge_repository
from .municipalities import get_municipality_profile

KEYWORD_TO_CLEN = {
    # Gradnja in objekti
    "gradnj": "52_clen", "dozidava": "52_clen", "nadzidava": "52_clen", "rekonstrukcija": "52_clen",
    "odstranitev": "52_clen", "sprememba namembnosti": "54_clen", "vrste objektov": "56_clen",
    "nezahtevni objekt": "64_clen", "enostavni objekt": "64_clen", "razpršena gradnja": "102_clen",
    "nelegalna gradnja": "103_clen",

    # Urejanje parcele
    "odmik": "58_clen", "odmiki": "58_clen", "soglasje soseda": "58_clen", "regulacijsk": "57_clen",
    "velikost parcele": "66_clen", "parcela objekta": "66_clen",
    "velikost objektov": "59_clen", "faktor izrabe": "59_clen", "FI": "59_clen", "faktor zazidanosti": "59_clen", "FZ": "59_clen",
    "višina objekt": "59_clen",

    # Oblikovanje
    "oblikovanj": "60_clen", "fasad": "60_clen", "streh": "60_clen", "kritina": "60_clen", "naklon strehe": "60_clen",
    "zelene površine": "61_clen", "FZP": "61_clen", "igrišče": "61_clen",

    # Infrastruktura
    "parkirišč": "62_clen", "parkirna mesta": "62_clen", "garaž": "62_clen", "število parkirnih mest": "63_clen",
    "komunaln": "67_clen", "priključek": "69_clen", "priključitev": "69_clen",
    "vodovod": "73_clen", "kanalizacij": "74_clen", "greznica": "69_clen", "čistilna naprava": "74_clen",
    "plinovod": "76_clen", "elektro": "77_clen", "daljnovod": "77_clen", "javna razsvetljava": "78_clen",
    "telekomunikacijsk": "79_clen", "komunikacijsk": "79_clen",

    # Varovanje in omejitve
    "varovalni pas": "70_clen", "varstvo narave": "81_clen", "kulturna dediščina": "82_clen",
    "vplivi na okolje": "83_clen", "varstvo voda": "85_clen", "vodotok": "85_clen",
    "priobalnem zemljišču": "85_clen", "vodovarstven": "86_clen",
    "varovalni gozd": "88_clen", "gozd s posebnim namenom": "89_clen",
    "hrup": "98_clen", "sevanje": "99_clen", "osončenj": "100_clen",
    "poplavn": "94_clen", "erozij": "92_clen", "plaz": "92_clen", "plazljiv": "92_clen",
    "potresn": "93_clen", "požar": "95_clen",

    # Ostalo
    "oglaševanj": "65_clen", "odpadk": "80_clen", "mineralne surovine": "90_clen",
    "obrambne potrebe": "96_clen", "zaklonišč": "96_clen",
    "invalid": "97_clen", "dostop za invalide": "97_clen", "arhitektonske ovire": "97_clen",
}

KEYWORD_PATTERNS: Dict[str, Pattern[str]] = {
    keyword: re.compile(re.escape(keyword), re.IGNORECASE)
    for keyword in KEYWORD_TO_CLEN
}


def format_structured_content(data_dict: Dict[str, Any]) -> str:
    lines = []
    for key, value in data_dict.items():
        if isinstance(value, dict):
            lines.append(f"\n- {key.replace('_', ' ').capitalize()}:")
            for sub_key, sub_value in value.items():
                lines.append(f"  - {sub_key.replace('_', ' ')}: {sub_value}")
        elif isinstance(value, list):
            lines.append(f"\n- {key.replace('_', ' ').capitalize()}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- {key.replace('_', ' ').capitalize()}: {value}")
    return "\n".join(lines)


def format_uredba_summary(uredba_data: Dict[str, Any]) -> str:
    if not uredba_data:
        return "Podatki iz UredbaObjekti.json niso na voljo."
    try:
        return json.dumps(uredba_data, ensure_ascii=False, indent=2)
    except Exception:
        return str(uredba_data)


@lru_cache(maxsize=4)
def load_knowledge_base(
    municipality_slug: str | None = None,
) -> Tuple[Dict, Dict, List, Dict, str, str]:
    profile = get_municipality_profile(municipality_slug)
    slug = profile.knowledge_slug
    knowledge_repository.ensure_bootstrap(slug, profile.name)

    opn_katalog = knowledge_repository.load_document_json(slug, "core", "opn")
    if not isinstance(opn_katalog, dict):
        opn_katalog = {}

    clen_data_map: Dict[str, Dict[str, Any]] = {}
    for cat_key, cat_data in opn_katalog.items():
        if "clen" in cat_data and "podrocja" in cat_data and isinstance(cat_data["podrocja"], dict):
            for raba_key, raba_data in cat_data["podrocja"].items():
                clen_data_map[raba_key.upper()] = {
                    "title": cat_data.get("naslov", ""),
                    "podrocje_naziv": raba_data.get("naziv", ""),
                    "content_structured": raba_data,
                    "parent_clen_key": f"{cat_data['clen']}_clen",
                }

    priloga1_data = knowledge_repository.load_document_json(slug, "priloge", "priloga1")
    priloga2_data = knowledge_repository.load_document_json(slug, "priloge", "priloga2")
    priloga34_data = knowledge_repository.load_document_json(slug, "priloge", "priloga3-4")
    izrazi_data_raw = knowledge_repository.load_document_json(slug, "priloge", "izrazi")

    priloge = {
        "priloga1": priloga1_data if isinstance(priloga1_data, dict) else {},
        "priloga2": priloga2_data if isinstance(priloga2_data, dict) else {},
        "priloga3": {},
        "priloga4": {},
        "Izrazi": izrazi_data_raw if isinstance(izrazi_data_raw, dict) else {},
    }
    if isinstance(priloga34_data, dict):
        priloge["priloga3"] = priloga34_data.get("priloga3", {}) or {}
        priloge["priloga4"] = priloga34_data.get("priloga4", {}) or {}

    all_eups = [
        item.get("enota_urejanja", "")
        for item in priloge.get("priloga2", {}).get("table_entries", [])
    ]
    all_eups.extend(
        [item.get("urejevalna_enota", "") for item in priloge.get("priloga3", {}).get("entries", [])]
    )
    unique_eups = sorted(list(set(filter(None, all_eups))), key=len, reverse=True)

    izrazi_data = priloge.get("Izrazi", {})
    izrazi_text = "\n".join([
        f"- **{term['term']}**: {term['definition']}"
        for term in izrazi_data.get("terms", [])
    ])

    uredba_text = knowledge_repository.load_document_text(slug, "priloge", "uredba-objekti")
    if not uredba_text:
        uredba_json = knowledge_repository.load_document_json(slug, "priloge", "uredba-objekti")
        if isinstance(uredba_json, dict):
            uredba_text = format_uredba_summary(uredba_json)

    return opn_katalog, priloge, unique_eups, clen_data_map, izrazi_text, uredba_text


def normalize_eup(eup_str: str) -> str:
    return eup_str.strip().upper() if eup_str else ""


def extract_referenced_namenske_rabe(
    content: str, clen_data_map: Optional[Dict[str, Any]] = None
) -> List[str]:
    if clen_data_map is None:
        _, _, _, clen_data_map, _, _ = load_knowledge_base()
    referenced = [
        m.upper()
        for pattern in [
            r"pogoj[ie]?\s+za\s+([A-Z]{1,3}[a-z]?)\b",
            r"kot\s+pri\s+([A-Z]{1,3}[a-z]?)\b",
            r"velj[a]?[jo]?\s+določila\s+za\s+([A-Z]{1,3}[a-z]?)\b",
            r"smiselno\s+velj[a]?[jo]?\s+za\s+([A-Z]{1,3}[a-z]?)\b",
            r"upoštev[a]?[jo]?\s+se\s+pogoj[ie]?\s+za\s+([A-Z]{1,3}[a-z]?)\b",
            r"skladno\s+s\s+pogoj[ie]?\s+za\s+([A-Z]{1,3}[a-z]?)\b",
            r"prevzem[a]?[jo]?\s+določila\s+za\s+([A-Z]{1,3}[a-z]?)\b",
            r"določila\s+za\s+([A-Z]{1,3}[a-z]?)\b",
        ]
        for m in re.findall(pattern, content, re.IGNORECASE)
    ]
    return [r for r in set(referenced) if r in clen_data_map]


def build_priloga1_text(
    namenska_raba: str, priloge: Optional[Dict[str, Any]] = None
) -> str:
    if priloge is None:
        _, priloge, _, _, _, _ = load_knowledge_base()
    priloga1_data = priloge.get("priloga1", {})
    if not priloga1_data:
        return "Priloga 1 ni na voljo."

    land_uses = priloga1_data.get("land_uses", [])
    objects = priloga1_data.get("objects", [])

    try:
        raba_index = -1
        for i, use in enumerate(land_uses):
            if namenska_raba.upper() in use.upper().replace(" ", ""):
                raba_index = i
                break
        if raba_index == -1:
            return f"Namenska raba '{namenska_raba}' ni najdena v Prilogi 1."
    except ValueError:
        return f"Namenska raba '{namenska_raba}' ni najdena v Prilogi 1."

    lines = [f"Za namensko rabo '{namenska_raba}' so dovoljeni naslednji enostavni/nezahtevni objekti:\n"]
    referenced_nrp = set()
    all_nrp_conditions = {k: v for obj in objects for k, v in obj.get("nrp_conditions", {}).items()}

    for obj in objects:
        lines.append(f"**{obj['title']}**")
        for subtype in obj.get("subtypes", []):
            permissions = subtype.get("permissions", [])
            if raba_index >= len(permissions):
                continue
            p_char = permissions[raba_index]
            if p_char == "●":
                p_text = "Dovoljeno po splošnih določilih."
            elif p_char == "x":
                p_text = "Ni dovoljeno."
            else:
                p_text = f"Dovoljeno pod posebnim pogojem št. {p_char}."
                referenced_nrp.add(p_char)

            subtype_desc = subtype.get("name") or obj.get("description")
            lines.append(f"- *{subtype_desc}*: {p_text}")

    if referenced_nrp:
        lines.append("\n**Legenda navedenih posebnih pogojev (NRP):**")
        for nrp_num in sorted(referenced_nrp):
            lines.append(f"- **Pogoj {nrp_num}**: {all_nrp_conditions.get(nrp_num, 'Opis ni na voljo.')}")

    return "\n".join(lines)


def build_requirements_from_db(
    eup_list: List[str],
    raba_list: List[str],
    project_text: str,
    municipality_slug: str | None = None,
) -> List[Dict[str, Any]]:
    opn_katalog, priloge, _, clen_data_map, _, _ = load_knowledge_base(
        municipality_slug
    )

    zahteve: List[Dict[str, Any]] = []
    dodani_cleni, dodane_namenske_rabe = set(), set()
    splosni_pogoji_katalog = opn_katalog.get(
        "splosni_prostorski_izvedbeni_pogoji", {}
    )
    original_rabe_upper = {
        r.strip().upper()
        for r in raba_list
        if isinstance(r, str) and r.strip()
    }

    triggered_optional_cleni: set[str] = set()
    if project_text:
        for keyword, pattern in KEYWORD_PATTERNS.items():
            if pattern.search(project_text):
                triggered_optional_cleni.add(KEYWORD_TO_CLEN[keyword])

    def add_podrobni_pogoji(raba_key: str, kategorija: str) -> None:
        raba_key = raba_key.upper()
        if raba_key in dodane_namenske_rabe:
            return
        clen_data = clen_data_map.get(raba_key)
        if not clen_data:
            return

        naslov = (
            f"{clen_data['parent_clen_key'].replace('_clen', '')}. člen - "
            f"{clen_data['podrocje_naziv']} ({raba_key})"
        )
        content = format_structured_content(clen_data["content_structured"])
        clen_label = f"{clen_data['parent_clen_key'].replace('_clen', '')}. člen"
        zahteve.append(
            {
                "kategorija": kategorija,
                "naslov": naslov,
                "besedilo": content,
                "clen": clen_label,
            }
        )
        dodane_namenske_rabe.add(raba_key)
        dodani_cleni.add(clen_data["parent_clen_key"])

        for ref_raba in extract_referenced_namenske_rabe(content, clen_data_map):
            if ref_raba not in original_rabe_upper:
                add_podrobni_pogoji(ref_raba, kategorija + " - Napotilo")

    for i in range(52, 104):
        clen_key = f"{i}_clen"
        is_mandatory = i <= 66
        if not is_mandatory and clen_key not in triggered_optional_cleni:
            continue
        if clen_key in dodani_cleni:
            continue

        content = splosni_pogoji_katalog.get(clen_key)
        if not content:
            continue
        naslov_match = re.search(r"^\s*\(([^)]+)\)", content)
        naslov = f"{i}. člen ({naslov_match.group(1)})" if naslov_match else f"{i}. člen"
        clen_label = f"{i}. člen"
        zahteve.append(
            {
                "kategorija": "Splošni prostorski izvedbeni pogoji (PIP)",
                "naslov": naslov,
                "besedilo": content,
                "clen": clen_label,
            }
        )
        dodani_cleni.add(clen_key)

    ciste_namenske_rabe = sorted(
        [r for r in original_rabe_upper if r in clen_data_map]
    )
    for raba in ciste_namenske_rabe:
        add_podrobni_pogoji(raba, "Podrobni prostorski izvedbeni pogoji (PIP NRP)")

    processed_eups = set()
    priloga2_entries = priloge.get("priloga2", {}).get("table_entries", [])
    for eup in eup_list:
        if not eup:
            continue
        normalized_eup = normalize_eup(eup)
        if normalized_eup in processed_eups:
            continue
        found_entry = None
        for entry in priloga2_entries:
            priloga_eup = normalize_eup(entry.get("enota_urejanja", ""))
            if priloga_eup == normalized_eup:
                found_entry = entry
                break
        if not found_entry:
            continue
        pip = found_entry.get("posebni_pip", "")
        if pip and pip.strip() and pip.strip() != "—":
            eup_name = found_entry.get("enota_urejanja", "")
            zahteve.append(
                {
                    "kategorija": "Posebni prostorski izvedbeni pogoji (PIP EUP)",
                    "naslov": f"Posebni PIP za EUP: {eup_name}",
                    "besedilo": pip,
                    "clen": found_entry.get("clen", ""),
                }
            )
            processed_eups.add(normalized_eup)

    if ciste_namenske_rabe:
        rabe_za_prilogo1 = [
            r
            for r in ciste_namenske_rabe
            if build_priloga1_text(r, priloge)
            != f"Namenska raba '{r}' ni najdena v Prilogi 1."
        ]
        if rabe_za_prilogo1:
            priloga1_sections = [
                f"--- Določila za {raba} --- \n{build_priloga1_text(raba, priloge)}"
                for raba in rabe_za_prilogo1
            ]
            priloga1_content = "\n\n" + "=" * 50 + "\n\n".join(priloga1_sections)
            naslov_rabe = ", ".join(rabe_za_prilogo1)
            zahteve.append(
                {
                    "kategorija": "Skladnost z Prilogo 1 (Enostavni/Nezahtevni objekti)",
                    "naslov": (
                        "Preverjanje dopustnosti enostavnih in nezahtevnih objektov za "
                        f"namenske rabe: {naslov_rabe}"
                    ),
                    "besedilo": priloga1_content,
                    "clen": "",
                }
            )

    for i, zahteva in enumerate(zahteve):
        zahteva["id"] = f"Z_{i}"
    return zahteve


def get_opn_katalog(municipality_slug: str | None = None) -> Dict[str, Any]:
    return load_knowledge_base(municipality_slug)[0]


def get_priloge(municipality_slug: str | None = None) -> Dict[str, Any]:
    return load_knowledge_base(municipality_slug)[1]


def get_all_eups(municipality_slug: str | None = None) -> List[str]:
    return load_knowledge_base(municipality_slug)[2]


def get_clen_data_map(municipality_slug: str | None = None) -> Dict[str, Any]:
    return load_knowledge_base(municipality_slug)[3]


def get_izrazi_text(municipality_slug: str | None = None) -> str:
    return load_knowledge_base(municipality_slug)[4]


def get_uredba_text(municipality_slug: str | None = None) -> str:
    return load_knowledge_base(municipality_slug)[5]


def search_knowledge_documents(
    query: str, municipality_slug: str | None = None, limit: int = 10
) -> List[Dict[str, Any]]:
    slug = municipality_slug or DEFAULT_MUNICIPALITY_SLUG
    results = knowledge_repository.search_documents(query, slug, limit)
    return [
        {
            "document_id": result.document_id,
            "municipality_slug": result.municipality_slug,
            "document_type": result.document_type,
            "slug": result.slug,
            "title": result.title or "",
            "snippet": result.snippet,
            "score": result.score,
        }
        for result in results
    ]


__all__ = [
    "KEYWORD_TO_CLEN",
    "KEYWORD_PATTERNS",
    "load_knowledge_base",
    "get_opn_katalog",
    "get_priloge",
    "get_all_eups",
    "get_clen_data_map",
    "get_izrazi_text",
    "get_uredba_text",
    "format_structured_content",
    "build_requirements_from_db",
    "build_priloga1_text",
    "normalize_eup",
    "extract_referenced_namenske_rabe",
    "search_knowledge_documents",
]
