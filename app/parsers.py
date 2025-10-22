"""Utilities for working with PDF sources."""
from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO, List, Optional, Union

from fastapi import HTTPException
from pypdf import PdfReader


PDFInput = Union[str, Path, bytes, BinaryIO]


def parse_pdf(source: PDFInput) -> str:
    try:
        if isinstance(source, (str, Path)):
            pdf = PdfReader(str(source))
        elif isinstance(source, bytes):
            pdf = PdfReader(io.BytesIO(source))
        else:
            if hasattr(source, "seek") and hasattr(source, "tell"):
                position = source.tell()
                source.seek(0)
                pdf = PdfReader(source)
                source.seek(position)
            else:
                pdf = PdfReader(source)
        text = "".join(page.extract_text() or "" for page in pdf.pages)
        return text.strip()
    except Exception as exc:  # pragma: no cover - depends on PDFs
        raise HTTPException(status_code=400, detail=f"Napaka pri branju PDF: {exc}") from exc


def parse_page_string(page_str: str) -> List[int]:
    if not page_str:
        return []
    pages = set()
    for part in page_str.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
            except ValueError:
                continue
            if start > 0 and end >= start:
                pages.update(range(start - 1, end))
        else:
            try:
                page_num = int(part)
            except ValueError:
                continue
            if page_num > 0:
                pages.add(page_num - 1)
    return sorted(list(pages))


def convert_pdf_pages_to_images(
    pdf_source: PDFInput, pages_to_render_str: Optional[str]
):
    import fitz  # type: ignore
    from PIL import Image

    images = []
    if not pages_to_render_str:
        return images
    page_numbers = parse_page_string(pages_to_render_str)
    if not page_numbers:
        return images

    try:
        if isinstance(pdf_source, (str, Path)):
            doc = fitz.open(str(pdf_source))
        elif isinstance(pdf_source, bytes):
            doc = fitz.open(stream=pdf_source, filetype="pdf")
        else:
            # File-like objekt
            position = None
            if hasattr(pdf_source, "tell"):
                position = pdf_source.tell()
            data = pdf_source.read()
            if position is not None and hasattr(pdf_source, "seek"):
                pdf_source.seek(position)
            doc = fitz.open(stream=data, filetype="pdf")
        for page_num in page_numbers:
            if 0 <= page_num < len(doc):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                # POMEMBNO: Naloži sliko v pomnilnik TAKOJ, preden se BytesIO zapre
                img.load()
                images.append(img)
        doc.close()
    except Exception as exc:  # pragma: no cover - depends on PDFs
        print(f"⚠️ Napaka pri pretvorbi PDF v slike: {exc}")
    return images


__all__ = ["parse_pdf", "convert_pdf_pages_to_images", "parse_page_string"]
