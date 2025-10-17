# app/routes.py

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import (APIRouter, BackgroundTasks, File, Form, HTTPException,
                   UploadFile)
from fastapi.responses import FileResponse, HTMLResponse

from .ai import (call_gemini_async, call_gemini_for_details_async,
                 call_gemini_for_key_data_async,
                 call_gemini_for_metadata_async, parse_ai_response)
from .cache import cache_manager
from .database import compute_session_summary, db_manager
from .files import save_revision_files
from .forms import generate_priloga_10a
from .frontend import build_homepage
from .knowledge_base import (IZRAZI_TEXT, UREDBA_TEXT,
                           build_requirements_from_db)
from .parsers import convert_pdf_pages_to_images, parse_pdf
from .prompts import build_prompt
from .reporting import generate_word_report
from .schemas import (AnalysisReportPayload, ConfirmReportPayload,
                    SaveSessionPayload)
from .temp_storage import (cleanup_session_storage, load_images_from_paths,
                           save_images_for_session)
from .utils import infer_project_name

logger = logging.getLogger(__name__)
router = APIRouter()

ANALYSIS_CHUNK_SIZE = 15

def chunk_list(data: List[Any], size: int) -> Iterable[List[Any]]:
    """Pomožna funkcija za razdelitev seznama v manjše sklope."""
    for i in range(0, len(data), size):
        yield data[i : i + size]

@router.get("/", response_class=HTMLResponse)
async def frontend() -> str:
    return build_homepage()

@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

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

@router.post("/extract-data")
async def extract_data(
    pdf_files: List[UploadFile] = File(...),
    files_meta_json: Optional[str] = Form(None),
):
    start_time = time.perf_counter()
    session_id = str(start_time)
    logger.info(
        f"[{session_id}] Začetek procesa /extract-data z {len(pdf_files)} datotekami."
    )

    page_overrides: Dict[str, str] = {}
    if files_meta_json:
        try:
            parsed = json.loads(files_meta_json)
            if isinstance(parsed, list):
                for entry in parsed:
                    if isinstance(entry, dict):
                        name, pages = entry.get("name"), entry.get("pages")
                        if name and isinstance(pages, str) and pages.strip():
                            page_overrides[name] = pages.strip()
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"[{session_id}] Neveljaven files_meta_json, ignoriram.")

    combined_text_parts, all_images, files_manifest = [], [], []
    for upload in pdf_files:
        pdf_bytes = await upload.read()
        if not pdf_bytes: continue
        file_label = upload.filename or "Dokument.pdf"
        text = parse_pdf(pdf_bytes)
        if text: combined_text_parts.append(f"=== VIR: {file_label} ===\n{text}")
        
        page_hint = page_overrides.get(file_label)
        if page_hint:
            try:
                images = convert_pdf_pages_to_images(pdf_bytes, page_hint)
                all_images.extend(images)
            except Exception as e:
                logger.warning(f"[{session_id}] Napaka pri pretvorbi slik za {file_label}: {e}")
        
        files_manifest.append({"filename": file_label, "pages": page_hint or "", "size": len(pdf_bytes)})

    if not combined_text_parts:
        raise HTTPException(status_code=400, detail="Iz naloženih datotek ni bilo mogoče prebrati besedila.")

    image_paths = await save_images_for_session(session_id, all_images)
    project_text = "\n\n".join(combined_text_parts)

    logger.info(f"[{session_id}] Začenjam vzporedne klice na Gemini API...")
    gemini_start_time = time.perf_counter()

    details_task = call_gemini_for_details_async(project_text, all_images)
    metadata_task = call_gemini_for_metadata_async(project_text)
    key_data_task = call_gemini_for_key_data_async(project_text, all_images)

    ai_details, metadata, key_data = await asyncio.gather(details_task, metadata_task, key_data_task)

    gemini_duration = time.perf_counter() - gemini_start_time
    logger.info(f"[{session_id}] Klici na Gemini API končani v {gemini_duration:.2f} sekundah.")

    session_data = {
        "project_text": project_text, "image_paths": image_paths, "metadata": metadata,
        "ai_details": ai_details, "key_data": key_data, "source_files": files_manifest
    }
    await cache_manager.store_session_data(session_id, session_data)

    response_data = {
        "session_id": session_id, "eup": ai_details.get("eup", []),
        "namenska_raba": ai_details.get("namenska_raba", []), **metadata, **key_data
    }

    total_duration = time.perf_counter() - start_time
    logger.info(f"[{session_id}] Celoten proces /extract-data je trajal {total_duration:.2f} sekund.")
    return response_data

@router.post("/analyze-report")
async def analyze_report(payload: AnalysisReportPayload):
    start_time = time.perf_counter()
    session_id = payload.session_id
    logger.info(f"[{session_id}] Začetek procesa /analyze-report s Pydantic modelom.")
    
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

    zahteve = build_requirements_from_db(final_eup_list_cleaned, final_raba_list_cleaned, data["project_text"])
    zahteve_za_analizo = [z for z in zahteve if z["id"] in payload.selected_ids] if payload.selected_ids else list(zahteve)

    if not zahteve_za_analizo:
        raise HTTPException(status_code=400, detail="Ni izbranih zahtev za analizo.")

    final_key_data = payload.key_data.dict()

    modified_project_text = f"""
        --- METAPODATKI PROJEKTA ---
        {data.get('metadata', {})}
        --- KLJUČNI GABARITNI IN LOKACIJSKI PODATKI PROJEKTA (Ekstrahirano in POTRJENO) ---
        {final_key_data}
        --- DOKUMENTACIJA (Besedilo in grafike) ---
        {data.get('project_text', '')}
        """

    zahteve_chunks = list(chunk_list(zahteve_za_analizo, ANALYSIS_CHUNK_SIZE))
    tasks = []
    for chunk in zahteve_chunks:
        prompt = build_prompt(modified_project_text, chunk, IZRAZI_TEXT, UREDBA_TEXT)
        task = call_gemini_async(prompt, images_for_analysis)
        tasks.append(task)
    
    logger.info(f"[{session_id}] Začenjam {len(tasks)} vzporednih klicev na Gemini za analizo...")
    gemini_start_time = time.perf_counter()
    ai_responses = await asyncio.gather(*tasks, return_exceptions=True)
    gemini_duration = time.perf_counter() - gemini_start_time
    logger.info(f"[{session_id}] Vzporedna analiza končana v {gemini_duration:.2f} sekundah.")

    combined_results_map = {**payload.existing_results_map}
    for response_obj, chunk in zip(ai_responses, zahteve_chunks):
        if isinstance(response_obj, Exception):
            logger.error(f"[{session_id}] Klic na Gemini za en sklop ni uspel: {response_obj}")
            continue
        try:
            chunk_results = parse_ai_response(response_obj, chunk)
            combined_results_map.update(chunk_results)
        except HTTPException as e:
            logger.error(f"[{session_id}] Napaka pri obdelavi enega od sklopov: {e.detail}")

    non_compliant_ids = [k for k, v in combined_results_map.items() if "nesklad" in v.get("skladnost", "").lower()]
    revisions = await db_manager.fetch_revisions(session_id)
    requirement_revisions = {}
    for rev in revisions:
        if rev_id := rev.get("requirement_id"):
            requirement_revisions.setdefault(rev_id, []).append(rev)

    final_report_data = {
        "zahteve": zahteve, "results_map": combined_results_map, "metadata": data.get("metadata", {}),
        "final_key_data": final_key_data, "source_files": data.get("source_files", [])
    }
    await cache_manager.store_session_data(f"report:{session_id}", final_report_data)

    total_duration = time.perf_counter() - start_time
    logger.info(f"[{session_id}] Celoten proces /analyze-report je trajal {total_duration:.2f} sekund.")

    return {
        "status": "success", "results_map": combined_results_map, "zahteve": zahteve,
        "non_compliant_ids": non_compliant_ids, "requirement_revisions": requirement_revisions,
    }

@router.post("/upload-revision")
async def upload_revision(
    session_id: str = Form(...),
    requirement_ids: str = Form(...),
    revision_files: List[UploadFile] = File(...),
    note: Optional[str] = Form(None),
    revision_pages: Optional[str] = Form(None),
):
    logger.info(f"[{session_id}] Sprejemam popravljeno dokumentacijo za dodatno analizo.")

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
        text = parse_pdf(pdf_bytes)
        if text:
            revision_text_parts.append(f"=== REVIZIJA: {filename} ===\n{text}")
        page_hint = page_overrides.get(filename)
        if page_hint:
            try:
                revision_images.extend(convert_pdf_pages_to_images(pdf_bytes, page_hint))
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
async def confirm_report(payload: ConfirmReportPayload, background_tasks: BackgroundTasks):
    session_id = payload.session_id
    logger.info(f"[{session_id}] Začetek procesa /confirm-report in generiranje poročil.")

    cache_key = f"report:{session_id}"
    cache = await cache_manager.retrieve_session_data(cache_key)
    if not cache:
        raise HTTPException(status_code=404, detail="Analiza za generiranje poročila ni na voljo.")

    excluded_ids = set(payload.excluded_ids or [])
    filtered_zahteve = [z for z in cache.get("zahteve", []) if z.get("id") not in excluded_ids]
    
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    metadata = cache.get("metadata", {})
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
        docx_path = await asyncio.to_thread(
            generate_word_report,
            filtered_zahteve, cache.get("results_map", {}), metadata, str(docx_output)
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