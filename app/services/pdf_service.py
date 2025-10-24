"""Servis za obdelavo PDF datotek z optimiziranim upravljanjem pomnilnika."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from fastapi import HTTPException, UploadFile

from ..config import MAX_PDF_SIZE_BYTES
from ..files import stream_upload_to_tempfile
from ..parsers import convert_pdf_pages_to_images, parse_pdf

logger = logging.getLogger(__name__)


class PDFService:
    """Servis za obdelavo PDF datotek."""

    @staticmethod
    async def process_pdf_files(
        pdf_files: List[UploadFile],
        page_overrides: Dict[str, str],
        session_id: str,
    ) -> Tuple[str, List, List[Dict]]:
        """Obdela seznam PDF datotek in vrne kombinirano besedilo, slike in manifest."""

        combined_text_parts: List[str] = []
        all_images = []
        files_manifest = []

        for upload in pdf_files:
            filename = getattr(upload, 'filename', 'unknown.pdf')
            logger.info(f"[{session_id}] Procesiranje datoteke: {filename}")
            
            async with stream_upload_to_tempfile(upload) as (temp_path, total_size):
                if total_size == 0 or temp_path is None:
                    logger.warning(
                        f"[{session_id}] Prazna datoteka ali napaka pri branju: {filename}. "
                        f"temp_path={temp_path}, total_size={total_size}"
                    )
                    continue

                if total_size > MAX_PDF_SIZE_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Datoteka '{upload.filename}' je prevelika "
                            f"(max {MAX_PDF_SIZE_BYTES // (1024*1024)}MB)"
                        ),
                    )

                file_label = upload.filename or "Dokument.pdf"

                # Ekstrahiraj besedilo brez nalaganja celotne datoteke v pomnilnik
                try:
                    text = await asyncio.to_thread(parse_pdf, temp_path)
                    if text:
                        combined_text_parts.append(f"=== VIR: {file_label} ===\n{text}")
                except Exception as exc:  # pragma: no cover - odvisno od PDF vsebine
                    logger.error(f"[{session_id}] Napaka pri branju {file_label}: {exc}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Napaka pri branju PDF '{file_label}': {str(exc)}",
                    ) from exc

                # Pretvori izbrane strani v slike, če je to zahtevano
                page_hint = page_overrides.get(file_label)
                if page_hint:
                    try:
                        images = await asyncio.to_thread(
                            convert_pdf_pages_to_images, temp_path, page_hint
                        )
                        all_images.extend(images)
                        logger.info(
                            f"[{session_id}] Pretvorjenih {len(images)} strani v slike za {file_label}"
                        )
                    except Exception as exc:  # pragma: no cover - odvisno od PDF vsebine
                        logger.warning(
                            f"[{session_id}] Napaka pri pretvorbi slik za {file_label}: {exc}"
                        )

                files_manifest.append(
                    {
                        "filename": file_label,
                        "pages": page_hint or "",
                        "size": total_size,
                    }
                )

        if not combined_text_parts:
            logger.error(
                f"[{session_id}] Ni bilo mogoče prebrati besedila iz nobene datoteke. "
                f"Naloženih datotek: {len(pdf_files)}, manifest: {files_manifest}"
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Iz naloženih datotek ({len(pdf_files)}) ni bilo mogoče prebrati besedila. "
                    f"Preverite, da so datoteke veljavni PDF-ji z besedilom."
                ),
            )

        combined_text = "\n\n".join(combined_text_parts)
        return combined_text, all_images, files_manifest

    @staticmethod
    async def process_pdf_files_from_paths(
        temp_files_data: List[Tuple[Path, str, str]],
        page_overrides: Dict[str, str],
        session_id: str,
    ) -> Tuple[str, List, List[Dict]]:
        """
        Obdela seznam PDF datotek iz začasnih poti in vrne kombinirano besedilo, slike in manifest.
        
        Args:
            temp_files_data: Seznam (temp_path, filename, content_type)
            page_overrides: Metapodatki za pretvorbo strani
            session_id: ID seje
            
        Returns:
            Tuple (combined_text, all_images, files_manifest)
        """
        combined_text_parts: List[str] = []
        all_images = []
        files_manifest = []

        for temp_path, filename, content_type in temp_files_data:
            if not temp_path.exists():
                logger.warning(f"[{session_id}] Začasna datoteka ne obstaja: {temp_path}")
                continue
            
            file_size = temp_path.stat().st_size
            
            if file_size == 0:
                logger.warning(f"[{session_id}] Prazna datoteka: {filename}")
                continue

            logger.info(f"[{session_id}] Procesiranje: {filename} ({file_size / (1024*1024):.2f}MB)")

            # Ekstrahiraj besedilo direktno iz poti
            try:
                text = await asyncio.to_thread(parse_pdf, temp_path)
                if text:
                    combined_text_parts.append(f"=== VIR: {filename} ===\n{text}")
                else:
                    logger.warning(f"[{session_id}] Ni besedila v datoteki: {filename}")
            except Exception as exc:
                logger.error(f"[{session_id}] Napaka pri branju {filename}: {exc}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Napaka pri branju PDF '{filename}': {str(exc)}",
                ) from exc

            # Pretvori izbrane strani v slike, če je to zahtevano
            page_hint = page_overrides.get(filename)
            if page_hint:
                try:
                    images = await asyncio.to_thread(
                        convert_pdf_pages_to_images, temp_path, page_hint
                    )
                    all_images.extend(images)
                    logger.info(
                        f"[{session_id}] Pretvorjenih {len(images)} strani v slike za {filename}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"[{session_id}] Napaka pri pretvorbi slik za {filename}: {exc}"
                    )

            files_manifest.append(
                {
                    "filename": filename,
                    "pages": page_hint or "",
                    "size": file_size,
                }
            )

        if not combined_text_parts:
            logger.error(
                f"[{session_id}] Ni bilo mogoče prebrati besedila iz nobene datoteke. "
                f"Število datotek: {len(temp_files_data)}, manifest: {files_manifest}"
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Iz naloženih datotek ({len(temp_files_data)}) ni bilo mogoče prebrati besedila. "
                    f"Preverite, da so datoteke veljavni PDF-ji z besedilom."
                ),
            )

        combined_text = "\n\n".join(combined_text_parts)
        return combined_text, all_images, files_manifest


__all__ = ["PDFService"]
