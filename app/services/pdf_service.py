# app/services/pdf_service.py

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Tuple

from fastapi import HTTPException, UploadFile

from ..config import MAX_PDF_SIZE_BYTES
from ..parsers import convert_pdf_pages_to_images, parse_pdf

logger = logging.getLogger(__name__)


class PDFService:
    """Servis za obdelavo PDF datotek."""

    @staticmethod
    async def process_pdf_files(
        pdf_files: List[UploadFile],
        page_overrides: Dict[str, str],
        session_id: str
    ) -> Tuple[str, List, List[Dict]]:
        """
        Obdela seznam PDF datotek in vrne kombinirano besedilo, slike in manifest.

        Args:
            pdf_files: Seznam naloženih PDF datotek
            page_overrides: Slovar z oznako strani za pretvorbo v slike
            session_id: ID seje za logiranje

        Returns:
            Tuple[combined_text, all_images, files_manifest]

        Raises:
            HTTPException(400): Če datoteke so prazne, prevelike ali neveljave
        """
        combined_text_parts: List[str] = []
        all_images = []
        files_manifest = []

        for upload in pdf_files:
            pdf_bytes = await upload.read()

            if not pdf_bytes:
                logger.warning(f"[{session_id}] Prazna datoteka: {upload.filename}")
                continue

            # Validacija velikosti
            if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Datoteka '{upload.filename}' je prevelika "
                           f"(max {MAX_PDF_SIZE_BYTES // (1024*1024)}MB)"
                )

            file_label = upload.filename or "Dokument.pdf"

            # Ekstrahiraj besedilo
            try:
                text = await asyncio.to_thread(parse_pdf, pdf_bytes)
                if text:
                    combined_text_parts.append(f"=== VIR: {file_label} ===\n{text}")
            except Exception as e:
                logger.error(f"[{session_id}] Napaka pri branju {file_label}: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Napaka pri branju PDF '{file_label}': {str(e)}"
                )

            # Pretvori strani v slike (če je določeno)
            page_hint = page_overrides.get(file_label)
            if page_hint:
                try:
                    images = await asyncio.to_thread(
                        convert_pdf_pages_to_images, pdf_bytes, page_hint
                    )
                    all_images.extend(images)
                    logger.info(f"[{session_id}] Pretvorjenih {len(images)} strani v slike za {file_label}")
                except Exception as e:
                    logger.warning(f"[{session_id}] Napaka pri pretvorbi slik za {file_label}: {e}")

            files_manifest.append({
                "filename": file_label,
                "pages": page_hint or "",
                "size": len(pdf_bytes)
            })

        if not combined_text_parts:
            raise HTTPException(
                status_code=400,
                detail="Iz naloženih datotek ni bilo mogoče prebrati besedila."
            )

        combined_text = "\n\n".join(combined_text_parts)
        return combined_text, all_images, files_manifest


__all__ = ["PDFService"]
