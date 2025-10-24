# app/routes.py

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                   HTTPException, UploadFile)
from fastapi.responses import FileResponse, HTMLResponse

from .cache import cache_manager
from .config import ANALYSIS_CHUNK_SIZE
from .database import compute_session_summary, db_manager
from .files import save_revision_files
from .forms import generate_priloga_10a
from .frontend import build_homepage
from .knowledge_base import (
    build_requirements_from_db,
    get_izrazi_text,
    get_uredba_text,
)
from .middleware import verify_api_key
from .municipalities import get_municipality_profile
from .parsers import convert_pdf_pages_to_images, parse_pdf
from .prompts import build_prompt
from .reporting import generate_word_report
from .schemas import (AnalysisReportPayload, ConfirmReportPayload,
                    SaveSessionPayload)
from .security import sanitize_ai_prompt_data, validate_pdf_upload
from .services import PDFService, ai_service
from .config import MAX_PDF_SIZE_BYTES
from .temp_storage import (cleanup_session_storage, load_images_from_paths,
                           save_images_for_session)
from .utils import infer_project_name

logger = logging.getLogger(__name__)
router = APIRouter()

def chunk_list(data: List[Any], size: int) -> Iterable[List[Any]]:
    """
    Razdeli seznam v manjše sklope.

    Args:
        data: Seznam za razdelitev
        size: Velikost vsakega sklopa

    Yields:
        Sklope seznama
    """
    for i in range(0, len(data), size):
        yield data[i : i + size]


def _parse_files_metadata(files_meta_json: Optional[str]) -> Dict[str, str]:
    """
    Parsira JSON metapodatke datotek.

    Args:
        files_meta_json: JSON string z metapodatki

    Returns:
        Dict[filename -> pages]
    """
    page_overrides: Dict[str, str] = {}
    if not files_meta_json:
        return page_overrides

    try:
        parsed = json.loads(files_meta_json)
        if isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, dict):
                    name, pages = entry.get("name"), entry.get("pages")
                    if name and isinstance(pages, str) and pages.strip():
                        page_overrides[name] = pages.strip()
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Neveljaven files_meta_json: {e}")

    return page_overrides

@router.get("/", response_class=HTMLResponse)
async def frontend() -> str:
    return build_homepage()

@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@router.get("/progress/{session_id}")
async def get_progress(session_id: str):
    """
    Vrne trenutni progress za dano sejo.

    Args:
        session_id: ID seje

    Returns:
        Dict s progress podatki ali None če ne obstaja
    """
    progress = await cache_manager.retrieve_session_data(f"progress:{session_id}")
    if not progress:
        logger.debug(f"[{session_id}] Progress podatki ne obstajajo, vračam privzete")
        return {"step": 0, "total_steps": 4, "message": "Inicializacija...", "percentage": 0}
    logger.debug(f"[{session_id}] Progress podatki: {progress}")
    return progress

@router.post("/save-session")
async def save_session(payload: SaveSessionPayload):
    session_id, data = payload.session_id.strip(), payload.data
    project_name = payload.project_name or infer_project_name(data)
    summary = payload.summary or compute_session_summary(data)
    await db_manager.upsert_session(session_id, project_name, summary, data)
    return {
        "message": "Analiza je shranjena.",
        "session_id": session_id,
        "project_name": project_name,
        "summary": summary,
    }

@router.get("/saved-sessions")
async def list_saved_sessions() -> Dict[str, List[Dict[str, Any]]]:
    rows = await db_manager.fetch_sessions()
    sessions: List[Dict[str, Any]] = []
    for row in rows:
        row_data = dict(row)
        sessions.append(
            {
                "session_id": row_data.get("session_id"),
                "project_name": row_data.get("project_name") or "Neimenovan projekt",
                "summary": row_data.get("summary") or "",
                "updated_at": row_data.get("updated_at"),
            }
        )

    return {"sessions": sessions}

@router.get("/saved-sessions/{session_id}")
async def get_saved_session(session_id: str):
    record = await db_manager.fetch_session(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Shranjena analiza ne obstaja.")
    revisions = await db_manager.fetch_revisions(session_id)
    record["revisions"] = revisions
    return record

@router.delete("/saved-sessions/{session_id}")
async def remove_saved_session(session_id: str):
    record = await db_manager.fetch_session(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Shranjena analiza ne obstaja.")
    await db_manager.delete_session(session_id)
    return {"message": "Shranjena analiza je izbrisana.", "session_id": session_id}


async def _process_extract_data_background(
    session_id: str,
    pdf_files: List[UploadFile],
    page_overrides: Dict[str, Any],
    municipality_slug: Optional[str],
):
    """
    Background task za procesiranje PDF datotek in AI analizo.

    Args:
        session_id: ID seje
        pdf_files: Seznam PDF datotek
        page_overrides: Metapodatki za pretvorbo strani
        municipality_slug: Oznaka občine
    """
    try:
        start_time = time.perf_counter()

        # Obdelva PDF datotek
        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 1,
            "total_steps": 4,
            "message": f"Ekstrakcija besedila iz {len(pdf_files)} PDF dokumentov...",
            "percentage": 10
        })

        project_text, all_images, files_manifest = await PDFService.process_pdf_files(
            pdf_files, page_overrides, session_id
        )

        # Shranjevanje slik
        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 2,
            "total_steps": 4,
            "message": "Analiza slik in priprava podatkov...",
            "percentage": 25
        })
        image_paths = await save_images_for_session(session_id, all_images)

        # Pridobitev profila občine
        profile = get_municipality_profile(municipality_slug)

        logger.info(f"[{session_id}] Začenjam vzporedne AI klice za občino {profile.slug}")
        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 3,
            "total_steps": 4,
            "message": "AI analiza dokumentacije (EUP, namenska raba, metapodatki)...",
            "percentage": 40
        })

        gemini_start_time = time.perf_counter()

        # Vzporedni AI klici
        ai_details, metadata, key_data = await asyncio.gather(
            ai_service.extract_eup_and_raba(project_text, all_images),
            ai_service.extract_metadata(project_text),
            ai_service.extract_key_data(project_text, all_images),
        )

        gemini_duration = time.perf_counter() - gemini_start_time
        logger.info(f"[{session_id}] AI klici končani v {gemini_duration:.2f}s")

        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 4,
            "total_steps": 4,
            "message": "Shranjevanje rezultatov...",
            "percentage": 85
        })

        # Združitev metapodatkov
        merged_metadata = {**profile.default_metadata, **metadata}
        investor_name = (merged_metadata.get("investitor") or "").strip()
        investor_address = (merged_metadata.get("investitor_naslov") or "").strip()
        merged_metadata["investitor1_ime"] = investor_name
        merged_metadata["investitor1_naslov"] = investor_address

        # Shranjevanje seje
        session_data = {
            "project_text": project_text,
            "image_paths": image_paths,
            "metadata": merged_metadata,
            "ai_details": ai_details,
            "key_data": key_data,
            "source_files": files_manifest,
            "municipality_slug": profile.slug,
            "municipality_name": profile.name,
        }
        await cache_manager.store_session_data(session_id, session_data)

        # Priprava podatkov za rezultat (shranjeno v cache za frontend)
        result_data = {
            "session_id": session_id,
            "municipality_slug": profile.slug,
            "municipality_name": profile.name,
            "eup": ai_details.get("eup", []),
            "namenska_raba": ai_details.get("namenska_raba", []),
            **merged_metadata,
            **key_data,
        }
        await cache_manager.store_session_data(f"result:{session_id}", result_data)

        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 4,
            "total_steps": 4,
            "message": "Končano!",
            "percentage": 100,
            "completed": True
        })

        total_duration = time.perf_counter() - start_time
        logger.info(f"[{session_id}] Proces končan v {total_duration:.2f}s")

    except Exception as e:
        logger.error(f"[{session_id}] Napaka pri procesiranju: {e}", exc_info=True)
        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 0,
            "total_steps": 4,
            "message": f"Napaka: {str(e)}",
            "percentage": 0,
            "completed": True,
            "error": True
        })


@router.post("/extract-data")
async def extract_data(
    background_tasks: BackgroundTasks,
    pdf_files: List[UploadFile] = File(...),
    files_meta_json: Optional[str] = Form(None),
    municipality_slug: Optional[str] = Form(None),
    api_key: str = Depends(verify_api_key),
):
    """
    Ekstrahira podatke iz naloženih PDF datotek in izvede začetno AI analizo.

    Args:
        background_tasks: FastAPI background tasks
        pdf_files: Seznam PDF datotek za analizo
        files_meta_json: Opcijski JSON z metapodatki (strani za pretvorbo)
        municipality_slug: Oznaka občine (privzeto iz config)
        api_key: API ključ za avtentikacijo

    Returns:
        Dict z session_id za polling progress-a

    Raises:
        HTTPException(400): Če datoteke ne vsebujejo besedila ali so neveljavne
        HTTPException(401): Če API ključ ni veljaven
        HTTPException(500): Če AI analiza ne uspe
    """
    start_time = time.perf_counter()
    # Generiraj kriptografsko varen naključni session ID
    # Uporabljamo secrets.token_urlsafe() namesto timestamp-a za preprečitev ugibanja session ID-jev
    session_id = secrets.token_urlsafe(32)
    logger.info(f"[{session_id}] Začetek /extract-data z {len(pdf_files)} datotekami")

    # VARNOSTNO: Validiraj vse PDF datoteke pred procesiranjem
    logger.info(f"[{session_id}] Začenjam validacijo {len(pdf_files)} PDF datotek...")
    for upload in pdf_files:
        try:
            await validate_pdf_upload(upload, MAX_PDF_SIZE_BYTES)
            # Eksplicitno resetiraj pozicijo po validaciji
            try:
                await upload.seek(0)
                logger.debug(f"[{session_id}] Validacija in reset uspešen za: {upload.filename}")
            except Exception as seek_error:
                logger.warning(f"[{session_id}] Seek(0) po validaciji ni uspel za {upload.filename}: {seek_error}")
                # Poskusi še z direktnim dostopom do file objekta
                if hasattr(upload, 'file') and hasattr(upload.file, 'seek'):
                    upload.file.seek(0)
                    logger.debug(f"[{session_id}] Alternativen seek(0) uspešen za: {upload.filename}")
        except ValueError as e:
            logger.error(f"[{session_id}] PDF validacija neuspešna za {upload.filename}: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Datoteka '{upload.filename}' ni veljavna: {str(e)}"
            )
    logger.info(f"[{session_id}] ✓ Vse PDF datoteke so veljavne")

    # Shrani začetni progress v cache za frontend polling
    progress_data = {
        "step": 1,
        "total_steps": 4,
        "message": "Procesiranje PDF datotek...",
        "percentage": 0
    }
    await cache_manager.store_session_data(f"progress:{session_id}", progress_data)
    logger.info(f"[{session_id}] Progress posodobljen: {progress_data}")

    # Parsiranje metapodatkov
    page_overrides = _parse_files_metadata(files_meta_json)

    # Začni procesiranje v ozadju
    background_tasks.add_task(
        _process_extract_data_background,
        session_id,
        pdf_files,
        page_overrides,
        municipality_slug
    )

    # Takoj vrni session_id, da lahko frontend začne polling
    return {"session_id": session_id, "status": "processing"}


@router.get("/extract-data/result/{session_id}")
async def get_extract_data_result(session_id: str):
    """
    Vrne rezultat ekstrakcije podatkov, ko je procesiranje končano.

    Args:
        session_id: ID seje

    Returns:
        Dict z ekstrahiranimi podatki ali napako
    """
    # Preveri progress
    progress = await cache_manager.retrieve_session_data(f"progress:{session_id}")
    if not progress:
        raise HTTPException(status_code=404, detail="Seja ne obstaja")

    if not progress.get("completed"):
        return {"status": "processing", "progress": progress}

    if progress.get("error"):
        return {"status": "error", "message": progress.get("message", "Napaka pri procesiranju")}

    # Pridobi rezultat
    result = await cache_manager.retrieve_session_data(f"result:{session_id}")
    if not result:
        raise HTTPException(status_code=404, detail="Rezultat ne obstaja")

    return {"status": "completed", "data": result}


async def _process_analyze_report_background(
    session_id: str,
    payload: AnalysisReportPayload,
):
    """
    Background task za analizo skladnosti zahtev.

    Args:
        session_id: ID seje
        payload: Podatki za analizo
    """
    try:
        start_time = time.perf_counter()

        data = await cache_manager.retrieve_session_data(session_id)
        if not data:
            raise HTTPException(status_code=404, detail="Seja je potekla ali ne obstaja.")

        image_paths = data.get("image_paths", [])
        images_for_analysis = await load_images_from_paths(image_paths) if image_paths else []
        logger.info(f"[{session_id}] Naloženih {len(images_for_analysis)} slik za podrobno analizo.")

        final_eup_list_cleaned = list(dict.fromkeys(e.strip() for e in payload.final_eup_list if e.strip()))
        final_raba_list_cleaned = list(dict.fromkeys(r.strip().upper() for r in payload.final_raba_list if r.strip()))

        if not final_raba_list_cleaned:
            raise HTTPException(status_code=400, detail="Namenska raba manjka.")

        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 2,
            "total_steps": 5,
            "message": "Generiranje zahtev skladnosti iz prostorskih aktov...",
            "percentage": 15
        })

        municipality_profile = get_municipality_profile(data.get("municipality_slug"))
        zahteve = build_requirements_from_db(
            final_eup_list_cleaned,
            final_raba_list_cleaned,
            data["project_text"],
            municipality_slug=municipality_profile.slug,
        )
        zahteve_za_analizo = [z for z in zahteve if z["id"] in payload.selected_ids] if payload.selected_ids else list(zahteve)

        if not zahteve_za_analizo:
            raise HTTPException(status_code=400, detail="Ni izbranih zahtev za analizo.")

        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 3,
            "total_steps": 5,
            "message": f"Pripravljam AI analizo za {len(zahteve_za_analizo)} zahtev...",
            "percentage": 30
        })

        final_key_data = payload.key_data.dict()

        # VARNOSTNO: Sanitiziraj vse uporabniške vnose pred uporabo v AI prompt-ih
        # To preprečuje prompt injection napade
        logger.info(f"[{session_id}] Sanitiziram podatke za AI prompt...")
        sanitized_data = sanitize_ai_prompt_data(
            project_text=data.get('project_text', ''),
            metadata=data.get('metadata', {}),
            key_data=final_key_data
        )
        logger.info(f"[{session_id}] Sanitizacija dokončana")

        municipality_context_lines = [
            f"Občina: {municipality_profile.name} (oznaka: {municipality_profile.slug})",
        ]
        if municipality_profile.prompt_context:
            municipality_context_lines.append(municipality_profile.prompt_context)
        municipality_context_lines.extend(
            f"- {rule}" for rule in municipality_profile.prompt_special_rules if rule
        )
        municipality_context_block = "\n".join(municipality_context_lines).strip()

        # Uporabimo sanitizirane podatke namesto originalnih
        modified_project_text = f"""
            --- METAPODATKI PROJEKTA ---
            {sanitized_data['metadata']}
            --- KONTEKST OBČINE ---
            {municipality_context_block}
            --- KLJUČNI GABARITNI IN LOKACIJSKI PODATKI PROJEKTA (Ekstrahirano in POTRJENO) ---
            {sanitized_data['key_data']}
            --- DOKUMENTACIJA (Besedilo in grafike) ---
            {sanitized_data['text']}
            """

        zahteve_chunks = list(chunk_list(zahteve_za_analizo, ANALYSIS_CHUNK_SIZE))
        izrazi_text = get_izrazi_text(municipality_profile.slug)
        uredba_text = get_uredba_text(municipality_profile.slug)
        tasks = []
        for chunk in zahteve_chunks:
            prompt = build_prompt(
                modified_project_text,
                chunk,
                izrazi_text,
                uredba_text,
                municipality_profile=municipality_profile,
            )
            task = ai_service.analyze_compliance(prompt, images_for_analysis)
            tasks.append(task)

        logger.info(f"[{session_id}] Začenjam {len(tasks)} vzporednih AI klicev")
        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 4,
            "total_steps": 5,
            "message": f"AI analiza poteka - to lahko traja 2-3 minute ({len(zahteve_za_analizo)} zahtev)...",
            "percentage": 40
        })

        gemini_start_time = time.perf_counter()
        ai_responses = await asyncio.gather(*tasks, return_exceptions=True)
        gemini_duration = time.perf_counter() - gemini_start_time
        logger.info(f"[{session_id}] AI analiza končana v {gemini_duration:.2f}s")

        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 5,
            "total_steps": 5,
            "message": "Procesiranje rezultatov...",
            "percentage": 90
        })

        combined_results_map = {**payload.existing_results_map}
        for response_obj, chunk in zip(ai_responses, zahteve_chunks):
            if isinstance(response_obj, Exception):
                logger.error(f"[{session_id}] AI klic za sklop ni uspel: {response_obj}")
                continue
            try:
                chunk_results = ai_service.parse_ai_response(response_obj, chunk)
                combined_results_map.update(chunk_results)
            except HTTPException as e:
                logger.error(f"[{session_id}] Napaka pri parsiranju: {e.detail}")

        non_compliant_ids = [k for k, v in combined_results_map.items() if "nesklad" in v.get("skladnost", "").lower()]
        revisions = await db_manager.fetch_revisions(session_id)
        requirement_revisions = {}
        for rev in revisions:
            if rev_id := rev.get("requirement_id"):
                requirement_revisions.setdefault(rev_id, []).append(rev)

        final_report_data = {
            "zahteve": zahteve,
            "results_map": combined_results_map,
            "metadata": data.get("metadata", {}),
            "final_key_data": final_key_data,
            "source_files": data.get("source_files", []),
            "municipality_slug": municipality_profile.slug,
            "municipality_name": municipality_profile.name,
        }
        await cache_manager.store_session_data(f"report:{session_id}", final_report_data)

        # Shrani rezultat za frontend
        analysis_result = {
            "status": "success",
            "results_map": combined_results_map,
            "zahteve": zahteve,
            "non_compliant_ids": non_compliant_ids,
            "requirement_revisions": requirement_revisions,
        }
        await cache_manager.store_session_data(f"analysis_result:{session_id}", analysis_result)

        final_progress_data = {
            "step": 5,
            "total_steps": 5,
            "message": "Analiza končana!",
            "percentage": 100,
            "completed": True
        }
        await cache_manager.store_session_data(f"progress:{session_id}", final_progress_data)
        logger.info(f"[{session_id}] Progress končan: {final_progress_data}")

        total_duration = time.perf_counter() - start_time
        logger.info(f"[{session_id}] Proces končan v {total_duration:.2f}s")

    except Exception as e:
        logger.error(f"[{session_id}] Napaka pri analizi: {e}", exc_info=True)
        await cache_manager.store_session_data(f"progress:{session_id}", {
            "step": 0,
            "total_steps": 5,
            "message": f"Napaka: {str(e)}",
            "percentage": 0,
            "completed": True,
            "error": True
        })


@router.post("/analyze-report")
async def analyze_report(
    background_tasks: BackgroundTasks,
    payload: AnalysisReportPayload,
    api_key: str = Depends(verify_api_key)
):
    """
    Izvede podrobno analizo skladnosti zahtev v ozadju.

    Args:
        background_tasks: FastAPI background tasks
        payload: Podatki za analizo (EUP, raba, ključni podatki, izbrane zahteve)
        api_key: API ključ za avtentikacijo

    Returns:
        Dict z session_id za polling progress-a

    Raises:
        HTTPException(400): Če manjkajo potrebni podatki
        HTTPException(404): Če seja ne obstaja
        HTTPException(500): Če AI analiza ne uspe
    """
    session_id = payload.session_id
    logger.info(f"[{session_id}] Začetek /analyze-report")

    # Initialize progress
    progress_data = {
        "step": 1,
        "total_steps": 5,
        "message": "Inicializacija analize skladnosti...",
        "percentage": 0
    }
    await cache_manager.store_session_data(f"progress:{session_id}", progress_data)
    logger.info(f"[{session_id}] Progress posodobljen: {progress_data}")

    # Preveri, ali seja obstaja
    data = await cache_manager.retrieve_session_data(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Seja je potekla ali ne obstaja.")

    # Začni procesiranje v ozadju
    background_tasks.add_task(
        _process_analyze_report_background,
        session_id,
        payload
    )

    # Takoj vrni session_id, da lahko frontend začne polling
    return {"session_id": session_id, "status": "processing"}


@router.get("/analyze-report/result/{session_id}")
async def get_analyze_report_result(session_id: str):
    """
    Vrne rezultat analize, ko je procesiranje končano.

    Args:
        session_id: ID seje

    Returns:
        Dict z rezultati analize ali napako
    """
    # Preveri progress
    progress = await cache_manager.retrieve_session_data(f"progress:{session_id}")
    if not progress:
        raise HTTPException(status_code=404, detail="Seja ne obstaja")

    if not progress.get("completed"):
        return {"status": "processing", "progress": progress}

    if progress.get("error"):
        return {"status": "error", "message": progress.get("message", "Napaka pri analizi")}

    # Pridobi rezultat
    result = await cache_manager.retrieve_session_data(f"analysis_result:{session_id}")
    if not result:
        raise HTTPException(status_code=404, detail="Rezultat ne obstaja")

    return {"status": "completed", "data": result}

@router.post("/upload-revision")
async def upload_revision(
    session_id: str = Form(...),
    requirement_ids: str = Form(...),
    revision_files: List[UploadFile] = File(...),
    note: Optional[str] = Form(None),
    revision_pages: Optional[str] = Form(None),
    api_key: str = Depends(verify_api_key),
):
    """
    Naloži popravljeno dokumentacijo za ponovno analizo.

    Args:
        session_id: ID seje
        requirement_ids: JSON seznam ID-jev zahtev za ponovno analizo
        revision_files: Seznam popravljenih PDF datotek
        note: Opcijska opomba
        revision_pages: JSON z oznakami strani
        api_key: API ključ za avtentikacijo

    Returns:
        Dict z statusom in podatki o reviziji
    """
    logger.info(f"[{session_id}] Sprejemam popravljeno dokumentacijo")

    session_data = await cache_manager.retrieve_session_data(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Seja ne obstaja ali je potekla.")

    note = note.strip() if note else None

    try:
        parsed_ids = json.loads(requirement_ids)
        if isinstance(parsed_ids, (str, int)):
            parsed_ids = [str(parsed_ids)]
        elif isinstance(parsed_ids, list):
            parsed_ids = [str(item) for item in parsed_ids if str(item).strip()]
        else:
            parsed_ids = []
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed_ids = []

    if not parsed_ids:
        raise HTTPException(status_code=400, detail="Ni izbranih zahtev za ponovno analizo.")

    page_overrides: Dict[str, str] = {}
    if revision_pages:
        try:
            parsed_pages = json.loads(revision_pages)
            if isinstance(parsed_pages, list):
                for entry in parsed_pages:
                    if isinstance(entry, dict):
                        name, pages = entry.get("name"), entry.get("pages")
                        if name and isinstance(pages, str) and pages.strip():
                            page_overrides[name] = pages.strip()
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"[{session_id}] Neveljaven revision_pages payload, ignoriram.")

    revision_text_parts: List[str] = []
    revision_images = []
    stored_files_payload = []

    for upload in revision_files:
        pdf_bytes = await upload.read()
        if not pdf_bytes:
            continue
        filename = upload.filename or "Popravek.pdf"
        stored_files_payload.append((filename, pdf_bytes, upload.content_type or "application/pdf"))
        text = await asyncio.to_thread(parse_pdf, pdf_bytes)
        if text:
            revision_text_parts.append(f"=== REVIZIJA: {filename} ===\n{text}")
        page_hint = page_overrides.get(filename)
        if page_hint:
            try:
                conversion_result = await asyncio.to_thread(
                    convert_pdf_pages_to_images, pdf_bytes, page_hint
                )
                revision_images.extend(conversion_result)
            except Exception as exc:
                logger.warning(f"[{session_id}] Napaka pri pretvorbi slik popravka {filename}: {exc}")

    if not stored_files_payload:
        raise HTTPException(status_code=400, detail="Ni veljavnih popravljenih dokumentov.")

    primary_requirement = parsed_ids[0] if len(parsed_ids) == 1 else None
    filenames, file_paths, mime_types = save_revision_files(
        session_id, stored_files_payload, requirement_id=primary_requirement
    )

    await db_manager.record_revision(
        session_id,
        filenames,
        file_paths,
        requirement_id=primary_requirement,
        note=note,
        mime_types=mime_types,
    )

    if revision_text_parts:
        timestamp = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
        header_lines = ["--- REVIZIJA DOKUMENTACIJE ---", f"Čas naložitve: {timestamp}"]
        if note:
            header_lines.append(f"Opomba: {note}")
        revision_block = "\n".join(header_lines + ["", "\n\n".join(revision_text_parts)])
        existing_text = session_data.get("project_text", "")
        session_data["project_text"] = f"{existing_text}\n\n{revision_block}" if existing_text else revision_block

    if revision_images:
        new_image_paths = await save_images_for_session(session_id, revision_images)
        session_data.setdefault("image_paths", [])
        session_data["image_paths"].extend(new_image_paths)

    revision_history = session_data.setdefault("revision_history", [])
    revision_history.append(
        {
            "filenames": filenames,
            "note": note or "",
            "uploaded_at": datetime.utcnow().isoformat(),
            "requirement_ids": parsed_ids,
        }
    )

    await cache_manager.store_session_data(session_id, session_data)

    revisions = await db_manager.fetch_revisions(session_id)
    requirement_revisions: Dict[str, List[Dict[str, Any]]] = {}
    for revision in revisions:
        req_id = revision.get("requirement_id")
        if req_id:
            requirement_revisions.setdefault(str(req_id), []).append(revision)

    logger.info(f"[{session_id}] Popravek shranjen. Pripravljen na ponovno analizo {len(parsed_ids)} zahtev.")

    return {
        "status": "success",
        "message": "Popravek je shranjen.",
        "requirement_revisions": requirement_revisions,
        "target_ids": parsed_ids,
    }

@router.post("/confirm-report")
async def confirm_report(
    payload: ConfirmReportPayload,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Potrdi analizo in generiraj Word/Excel poročila.

    Args:
        payload: Podatki za generiranje poročila
        background_tasks: FastAPI background tasks za cleanup
        api_key: API ključ za avtentikacijo

    Returns:
        Dict s potmi do generiranih datotek
    """
    session_id = payload.session_id
    logger.info(f"[{session_id}] Začetek /confirm-report in generiranje poročil")

    cache_key = f"report:{session_id}"
    cache = await cache_manager.retrieve_session_data(cache_key)
    if not cache:
        raise HTTPException(status_code=404, detail="Analiza za generiranje poročila ni na voljo.")

    results_updated = False
    if payload.updated_results_map:
        existing_map_raw = cache.get("results_map") or {}
        existing_map = existing_map_raw if isinstance(existing_map_raw, dict) else {}

        merged_map: Dict[Any, Dict[str, Any]] = {}
        existing_key_lookup: Dict[str, Any] = {}
        preferred_type: Optional[type] = None

        for existing_key, existing_value in existing_map.items():
            merged_map[existing_key] = existing_value.copy() if isinstance(existing_value, dict) else existing_value
            existing_key_lookup[str(existing_key)] = existing_key

        if existing_key_lookup:
            preferred_type = type(next(iter(existing_key_lookup.values())))

        for raw_key, value in payload.updated_results_map.items():
            if not isinstance(value, dict):
                continue

            target_key: Any = existing_key_lookup.get(str(raw_key), raw_key)

            if target_key is raw_key and preferred_type and not isinstance(raw_key, preferred_type):
                try:
                    coerced_key = preferred_type(raw_key)
                    if str(coerced_key) == str(raw_key):
                        target_key = coerced_key
                except (TypeError, ValueError):
                    pass

            if (
                target_key is raw_key
                and isinstance(raw_key, str)
                and raw_key.isdigit()
                and preferred_type is int
            ):
                try:
                    target_key = int(raw_key)
                except ValueError:
                    pass

            base_value = merged_map.get(target_key, {})
            merged_map[target_key] = {**base_value, **value} if isinstance(base_value, dict) else value.copy()
            existing_key_lookup[str(target_key)] = target_key
            results_updated = True

        if results_updated:
            cache["results_map"] = merged_map

    key_data_updated = False
    if payload.updated_key_data:
        existing_key_data = cache.get("final_key_data")
        merged_key_data: Dict[str, Any] = {}
        if isinstance(existing_key_data, dict):
            merged_key_data.update(existing_key_data)
        if isinstance(payload.updated_key_data, dict):
            merged_key_data.update(payload.updated_key_data)
            key_data_updated = True
        if key_data_updated:
            cache["final_key_data"] = merged_key_data

    if results_updated or key_data_updated:
        await cache_manager.store_session_data(cache_key, cache)

    excluded_ids = set(payload.excluded_ids or [])
    filtered_zahteve = [z for z in cache.get("zahteve", []) if z.get("id") not in excluded_ids]

    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    metadata = cache.get("metadata", {})

    # Dodaj številko zadeve v metadata če je bila podana
    if payload.stevilka_zadeve:
        metadata["stevilka_zadeve"] = payload.stevilka_zadeve.strip()
    investor_name = (metadata.get("investitor") or "").strip()
    if investor_name:
        safe_investor = re.sub(r"\s+", "_", investor_name, flags=re.UNICODE)
        safe_investor = re.sub(r"[^\w.-]", "", safe_investor, flags=re.UNICODE)
        if not safe_investor:
            safe_investor = "Neznan_investitor"
        docx_filename = f"Poročilo_skladnosti_{safe_investor}.docx"
    else:
        docx_filename = f"Poročilo_skladnosti_{timestamp}.docx"

    docx_output = reports_dir / docx_filename
    if docx_output.exists():
        docx_output = reports_dir / f"{docx_output.stem}_{timestamp}{docx_output.suffix}"

    xlsx_output = reports_dir / f"Priloga10A_{timestamp}.xlsx"

    try:
        # Generiraj Word poročilo s formatom (full ali summary)
        report_format = payload.report_format if payload.report_format in ["full", "summary"] else "full"
        docx_path = await asyncio.to_thread(
            generate_word_report,
            filtered_zahteve, cache.get("results_map", {}), metadata, str(docx_output), report_format
        )
        xlsx_path = await asyncio.to_thread(
            generate_priloga_10a,
            filtered_zahteve, cache.get("results_map", {}), metadata,
            cache.get("final_key_data", {}), cache.get("source_files", []), str(xlsx_output)
        )
    except Exception as e:
        logger.error(f"[{session_id}] Napaka pri generiranju poročil: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Napaka pri generiranju datotek poročila.")

    background_tasks.add_task(cache_manager.delete_session_data, session_id)
    background_tasks.add_task(cache_manager.delete_session_data, cache_key)
    background_tasks.add_task(cleanup_session_storage, session_id)

    logger.info(f"[{session_id}] Poročila generirana. Seja zaključena in počiščena.")
    return {"status": "success", "docx_path": docx_path, "xlsx_path": xlsx_path}

# Tukaj lahko dodate še ostale poti, kot so /download, /upload-revision itd.