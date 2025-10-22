"""Servis za obdelavo PDF datotek z optimiziranim upravljanjem pomnilnika."""
from __future__ import annotations

import asyncio
import logging
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
            async with stream_upload_to_tempfile(upload) as (temp_path, total_size):
                if total_size == 0 or temp_path is None:
                    logger.warning(f"[{session_id}] Prazna datoteka: {upload.filename}")
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
            raise HTTPException(
                status_code=400,
                detail="Iz naloženih datotek ni bilo mogoče prebrati besedila.",
            )

        combined_text = "\n\n".join(combined_text_parts)
        return combined_text, all_images, files_manifest


__all__ = ["PDFService"]
