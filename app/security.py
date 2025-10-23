# app/security.py
"""
Varnostni moduli za zaščito pred različnimi vrstami napadov.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Union

from fastapi import UploadFile
from pydantic import BaseModel, validator

logger = logging.getLogger(__name__)

# Dovoljeni MIME types za PDF datoteke
ALLOWED_PDF_MIME_TYPES = [
    "application/pdf",
    "application/x-pdf",
]

# PDF magic bytes (mora se začeti z)
PDF_MAGIC_BYTES = b'%PDF-'

# Nevarne vsebine v PDF-jih
DANGEROUS_PDF_PATTERNS = [
    b'/JavaScript',  # PDF z JavaScript
    b'/JS',
    b'/EmbeddedFile',  # Priložene datoteke
    b'/Launch',  # Zagon zunanjih programov
    b'/OpenAction',  # Avtomatski zagon akcij ob odprtju
    b'/AA',  # Additional Actions (lahko nevarno)
    b'/GoToE',  # External Go-To
    b'/RichMedia',  # Embedded multimedia
]

# Nevarne fraze, ki lahko nakazujejo prompt injection poskus
DANGEROUS_PROMPT_PATTERNS = [
    # Angleške fraze
    r'IGNORE\s+(PREVIOUS|ALL|ABOVE)\s+(INSTRUCTIONS?|PROMPTS?|RULES?|COMMANDS?)',
    r'DISREGARD\s+(PREVIOUS|ALL|ABOVE)',
    r'OVERRIDE\s+(SYSTEM|INSTRUCTIONS?|SETTINGS?)',
    r'BYPASS\s+(VALIDATION|SECURITY|CHECKS?|RULES?)',
    r'SKIP\s+(VALIDATION|CHECKS?|RULES?)',
    r'FORGET\s+(EVERYTHING|ALL|PREVIOUS)',
    r'NEW\s+INSTRUCTIONS?:',
    r'ACT\s+AS\s+(IF|A|AN)',
    r'PRETEND\s+(TO\s+BE|YOU\s+ARE)',
    r'SIMULATE\s+',
    r'ROLPLAY\s+',
    r'JAILBREAK',

    # Slovenske fraze
    r'IGNORIRAJ\s+(PREJŠNJ[AE]|VS[AE]|ZGORNJI[AE])\s+(NAVODIL[AO]|UKAZ[E]?|PRAVIL[AO])',
    r'PREZRI\s+(PREJŠNJ[AE]|VS[AE])',
    r'RAZVELJAVI\s+(SISTEM|NAVODIL[AO])',
    r'OBVE[ŽZ]I\s+(VALIDACIJ[OA]|VARNOST|PREVERJANJ[AE])',
    r'PRESKOČI\s+(VALIDACIJ[OA]|PREVERJANJ[AE]|PRAVIL[AO])',
    r'POZABI\s+(VSE|PREJŠNJ[AE])',
    r'NOVA?\s+NAVODIL[AO]:',
    r'DELUJ\s+TAKO\s+KOT',
    r'PRETVARJA[JL]\s+SE',

    # Sistemski ukazi
    r'<\s*SYSTEM\s*>',
    r'<\s*\/?\s*ADMIN\s*>',
    r'<\s*\/?\s*ROOT\s*>',
    r'\[\s*SYSTEM\s*\]',

    # Poskusi manipulacije JSON output-a
    r'"skladnost"\s*:\s*"Skladno"',  # Direkten poskus nastavitve skladnosti
    r'"status"\s*:\s*"(approved|skladno|pass)"',
]

# Kompajliraj regex pattern-e za hitrejšo izvedbo
COMPILED_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    for pattern in DANGEROUS_PROMPT_PATTERNS
]


def sanitize_text_for_prompt(text: str, field_name: str = "text") -> str:
    """
    Sanitizira tekst za varno uporabo v AI prompt-ih.

    Odstrani ali označi nevarne vzorce, ki bi lahko manipulirali AI odgovore.

    Args:
        text: Tekst za sanitizacijo
        field_name: Ime polja (za logiranje)

    Returns:
        Sanitiziran tekst
    """
    if not text or not isinstance(text, str):
        return text

    original_text = text
    detections = []

    # Preveri za nevarne vzorce
    for i, pattern in enumerate(COMPILED_PATTERNS):
        matches = pattern.findall(text)
        if matches:
            detections.append({
                "pattern_id": i,
                "pattern": DANGEROUS_PROMPT_PATTERNS[i],
                "matches": matches[:3]  # Samo prvih 5 za logiranje
            })
            # Zamenjaj nevarne fraze z opozorilom
            text = pattern.sub('[ODSTRANJENA POTENCIALNO NEVARNA VSEBINA]', text)

    # Logiraj, če so bili zaznani poskusi
    if detections:
        logger.warning(
            f"⚠️ Prompt injection zaznava v '{field_name}': "
            f"Najdenih {len(detections)} sumljivih vzorcev. "
            f"Vzorci: {[d['pattern'] for d in detections[:3]]}"
        )
        logger.debug(f"Detajli zaznave: {json.dumps(detections, ensure_ascii=False, indent=2)}")

    # Dodatna sanitizacija
    # Odstrani HTML/XML tags (preprečitev XSS in manipulacije)
    text = re.sub(r'<[^>]+>', '', text)

    # Omejitev ponavljajočih se znakov (DOS preprečitev)
    text = re.sub(r'(.)\1{50,}', r'\1' * 10, text)  # Max 10 ponovitev

    return text


def validate_json_structure(data: Any, expected_keys: List[str]) -> bool:
    """
    Validira, da JSON vsebuje pričakovane ključe in strukturo.

    Args:
        data: JSON podatki za validacijo
        expected_keys: Seznam pričakovanih ključev

    Returns:
        True, če je struktura veljavna
    """
    if not isinstance(data, dict):
        return False

    for key in expected_keys:
        if key not in data:
            logger.warning(f"Manjkajoč pričakovan ključ v JSON: {key}")
            return False

    return True


class SafeProjectData(BaseModel):
    """
    Pydantic model za varno shranjevanje projektnih podatkov.
    Sanitizira vse tekstovne vnose za preprečitev prompt injection.
    """

    text: str
    metadata: Dict[str, Any]
    key_data: Dict[str, Any]

    @validator('text', pre=True)
    def sanitize_text(cls, v):
        """Sanitiziraj glavni tekst projekta."""
        if not v:
            return v
        return sanitize_text_for_prompt(str(v), "project_text")

    @validator('metadata', pre=True)
    def sanitize_metadata(cls, v):
        """Sanitiziraj metapodatke."""
        if not isinstance(v, dict):
            return v

        sanitized = {}
        for key, value in v.items():
            if isinstance(value, str):
                sanitized[key] = sanitize_text_for_prompt(value, f"metadata.{key}")
            else:
                sanitized[key] = value

        return sanitized

    @validator('key_data', pre=True)
    def sanitize_key_data(cls, v):
        """Sanitiziraj ključne podatke."""
        if not isinstance(v, dict):
            return v

        sanitized = {}
        for key, value in v.items():
            if isinstance(value, str):
                sanitized[key] = sanitize_text_for_prompt(value, f"key_data.{key}")
            else:
                sanitized[key] = value

        return sanitized


class SafeAIResponse(BaseModel):
    """
    Pydantic model za validacijo AI odgovorov.
    Zagotavlja, da AI vrne pričakovano strukturo.
    """

    eup: List[str] = []
    namenska_raba: List[str] = []

    @validator('eup', 'namenska_raba')
    def validate_list_items(cls, v):
        """Validiraj, da so vsi elementi seznama strings."""
        if not isinstance(v, list):
            return []
        return [str(item) for item in v if item]


class SafeComplianceResult(BaseModel):
    """
    Pydantic model za validacijo rezultatov analize skladnosti.
    """

    id: str
    obrazlozitev: str
    evidence: str
    skladnost: str
    predlagani_ukrep: str

    @validator('skladnost')
    def validate_compliance_status(cls, v):
        """Validiraj, da je status skladnosti eden od dovoljenih."""
        allowed_statuses = ['Skladno', 'Neskladno', 'Ni relevantno', 'Neznano']
        if v not in allowed_statuses:
            logger.warning(f"Neveljaven status skladnosti: {v}. Nastavljam 'Neznano'.")
            return 'Neznano'
        return v


def sanitize_ai_prompt_data(
    project_text: str,
    metadata: Dict[str, Any],
    key_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Centralna funkcija za sanitizacijo vseh podatkov pred uporabo v AI prompt-ih.

    Args:
        project_text: Besedilo projekta iz PDF-jev
        metadata: Metapodatki projekta
        key_data: Ključni podatki projekta

    Returns:
        Dictionary s sanitiziranimi podatki
    """
    try:
        safe_data = SafeProjectData(
            text=project_text,
            metadata=metadata,
            key_data=key_data
        )

        return {
            "text": safe_data.text,
            "metadata": safe_data.metadata,
            "key_data": safe_data.key_data
        }

    except Exception as e:
        logger.error(f"Napaka pri sanitizaciji podatkov: {e}", exc_info=True)
        # V primeru napake vrnemo zelo konservativno sanitizirane podatke
        return {
            "text": sanitize_text_for_prompt(str(project_text), "fallback_text"),
            "metadata": {},
            "key_data": {}
        }


def validate_session_id(session_id: str) -> bool:
    """
    Validira format session ID-ja.

    Session ID mora biti:
    - Dolg med 1 in 255 znaki
    - Vsebuje samo alfanumerične znake, pomišljaje in podčrtaje

    Args:
        session_id: Session ID za validacijo

    Returns:
        True, če je session ID veljaven

    Raises:
        ValueError: Če session ID ni veljaven
    """
    if not session_id or not isinstance(session_id, str):
        raise ValueError("Session ID ne sme biti prazen")

    if len(session_id) > 255:
        raise ValueError("Session ID je predolg (max 255 znakov)")

    # Dovoljeni samo alfanumerični znaki, _, -, .
    if not re.match(r'^[a-zA-Z0-9_.-]+$', session_id):
        raise ValueError(
            f"Session ID vsebuje neveljavne znake. "
            f"Dovoljeni so samo: a-z, A-Z, 0-9, _, -, ."
        )

    return True


def validate_path_safety(path: Path, allowed_base: Path) -> bool:
    """
    Preveri, da pot ostaja znotraj dovoljenega direktorija.

    Preprečuje path traversal napade (npr. ../../etc/passwd).

    Args:
        path: Pot za preverjanje
        allowed_base: Dovoljeni osnovni direktorij

    Returns:
        True, če je pot varna

    Raises:
        ValueError: Če pot ni varna
    """
    try:
        # Razreši absolutne poti
        resolved_path = path.resolve()
        resolved_base = allowed_base.resolve()

        # Preveri, da je pot relativna znotraj base
        if not resolved_path.is_relative_to(resolved_base):
            raise ValueError(
                f"Path traversal poskus zaznan: pot {resolved_path} "
                f"ni znotraj dovoljenega direktorija {resolved_base}"
            )

        return True

    except Exception as e:
        logger.error(f"Napaka pri validaciji poti: {e}")
        raise ValueError(f"Neveljaven pot: {e}")


async def validate_pdf_upload(upload: UploadFile, max_size_bytes: int) -> bytes:
    """
    Varno validira naloženo PDF datoteko.

    Preveri:
    - MIME type
    - PDF magic bytes
    - Nevarne vsebine (JavaScript, embedded files, itd.)
    - Velikost datoteke

    Args:
        upload: UploadFile objekt iz FastAPI
        max_size_bytes: Maksimalna dovoljena velikost v bytih

    Returns:
        Prva chunk bytov datoteke (za nadaljnjo obdelavo)

    Raises:
        ValueError: Če datoteka ni veljavna ali vsebuje nevarne elemente
    """
    # 1. Preveri MIME type
    if upload.content_type not in ALLOWED_PDF_MIME_TYPES:
        raise ValueError(
            f"Neveljavna vrsta datoteke. "
            f"Dovoljene so samo PDF datoteke (application/pdf). "
            f"Prejeto: {upload.content_type}"
        )

    # 2. Preberi prvi chunk za validacijo
    # Beremo 1MB, kar je dovolj za preverjanje headerjev in začetne vsebine
    chunk_size = 1024 * 1024  # 1MB
    first_chunk = await upload.read(chunk_size)

    if not first_chunk:
        raise ValueError("Datoteka je prazna")

    # 3. Preveri PDF magic bytes
    if not first_chunk.startswith(PDF_MAGIC_BYTES):
        raise ValueError(
            "Datoteka ni veljaven PDF. "
            "PDF datoteka se mora začeti z '%PDF-' magic bytes."
        )

    # 4. Preveri za nevarne vzorce
    detections = []
    for pattern in DANGEROUS_PDF_PATTERNS:
        if pattern in first_chunk:
            detections.append(pattern.decode('latin-1'))

    if detections:
        logger.warning(
            f"PDF vsebuje potencialno nevarne elemente: {detections}. "
            f"Datoteka: {upload.filename}"
        )
        raise ValueError(
            f"PDF vsebuje nedovoljene elemente: {', '.join(detections)}. "
            f"Iz varnostnih razlogov takšne datoteke niso dovoljene."
        )

    # 5. Preveri velikost datoteke
    # Ponastavimo pozicijo in preberemo vso datoteko
    await upload.seek(0)
    file_size = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        file_size += len(chunk)

        if file_size > max_size_bytes:
            raise ValueError(
                f"Datoteka je prevelika. "
                f"Maksimalna velikost: {max_size_bytes / (1024*1024):.1f}MB. "
                f"Velikost datoteke: {file_size / (1024*1024):.1f}MB."
            )

    # Ponastavimo pozicijo na začetek za nadaljnjo obdelavo
    await upload.seek(0)

    logger.info(
        f"✓ PDF validacija uspešna: {upload.filename} "
        f"({file_size / (1024*1024):.2f}MB)"
    )

    return first_chunk


__all__ = [
    "sanitize_text_for_prompt",
    "sanitize_ai_prompt_data",
    "SafeProjectData",
    "SafeAIResponse",
    "SafeComplianceResult",
    "validate_json_structure",
    "validate_session_id",
    "validate_path_safety",
    "validate_pdf_upload",
]
