"""File-system helpers for storing uploaded revisions."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from inspect import isawaitable
from pathlib import Path
from typing import AsyncIterator, BinaryIO, Iterable, List, Tuple, Union

from fastapi import UploadFile

from .config import DATA_DIR

REVISION_ROOT = DATA_DIR / "revisions"
REVISION_ROOT.mkdir(parents=True, exist_ok=True)

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _sanitize_path_component(value: str, fallback: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", value)
    return cleaned.strip("._")[:255] or fallback


def sanitize_filename(filename: str) -> str:
    if not filename:
        return "datoteka.pdf"
    base_name = os.path.basename(filename)
    return _sanitize_path_component(base_name, "datoteka.pdf")


ContentType = Union[bytes, Path, BinaryIO]


def save_revision_files(
    session_id: str,
    files: Iterable[Tuple[str, ContentType, str]],
    requirement_id: str | None = None,
) -> Tuple[List[str], List[str], List[str]]:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    session_part = _sanitize_path_component(session_id, "session")
    requirement_part = _sanitize_path_component(requirement_id or "full", "full")
    folder_parts = [session_part, requirement_part]
    target_dir = REVISION_ROOT.joinpath(*folder_parts)
    target_dir.mkdir(parents=True, exist_ok=True)

    filenames: List[str] = []
    file_paths: List[str] = []
    mime_types: List[str] = []

    for original_name, content, mime in files:
        safe_name = sanitize_filename(original_name)
        stored_name = f"{timestamp}_{safe_name}"
        destination = target_dir / stored_name
        _write_content(destination, content)
        filenames.append(original_name or safe_name)
        file_paths.append(str(destination.relative_to(DATA_DIR)))
        mime_types.append(mime or "application/octet-stream")
    return filenames, file_paths, mime_types


def _write_content(destination: Path, content: ContentType) -> None:
    if isinstance(content, bytes):
        destination.write_bytes(content)
    elif isinstance(content, Path):
        shutil.copyfile(content, destination)
    elif hasattr(content, "read"):
        with destination.open("wb") as out_file:
            shutil.copyfileobj(content, out_file)
    else:
        raise TypeError("Nepodprta vrsta vsebine pri shranjevanju datoteke.")


def _detect_suffix(candidate: object) -> str:
    """Extract a meaningful suffix for temporary files."""

    if isinstance(candidate, (str, Path)):
        return Path(candidate).suffix

    for attr in ("filename", "name"):
        value = getattr(candidate, attr, None)
        if isinstance(value, str):
            return Path(value).suffix

    return ""


def _copy_sync_to_tempfile(
    source: Union[str, Path, BinaryIO], chunk_size: int
) -> Tuple[Path, int]:
    suffix = _detect_suffix(source)
    total_size = 0

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        temp_path = Path(tmp.name)

        if isinstance(source, (str, Path)):
            source_path = Path(source)
            with source_path.open("rb") as src:
                shutil.copyfileobj(src, tmp)
            total_size = source_path.stat().st_size
        else:
            file_obj = source
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)

            while True:
                chunk = file_obj.read(chunk_size)
                if not chunk:
                    break
                tmp.write(chunk)
                total_size += len(chunk)

    return temp_path, total_size


@asynccontextmanager
async def stream_upload_to_tempfile(
    upload: Union[UploadFile, str, Path, BinaryIO],
    chunk_size: int = 1024 * 1024,
) -> AsyncIterator[Tuple[Path | None, int]]:
    temp_path: Path | None = None
    total_size = 0

    try:
        if isinstance(upload, UploadFile):
            seek = getattr(upload, "seek", None)
            if callable(seek):
                try:
                    result = seek(0)
                    if isawaitable(result):
                        await result
                except Exception:
                    file_obj = getattr(upload, "file", None)
                    if file_obj and hasattr(file_obj, "seek"):
                        file_obj.seek(0)

            suffix = _detect_suffix(upload)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                while True:
                    chunk = await upload.read(chunk_size)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    tmp.write(chunk)
                temp_path = Path(tmp.name)
        else:
            temp_path, total_size = _copy_sync_to_tempfile(upload, chunk_size)

        yield temp_path, total_size
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


__all__ = ["sanitize_filename", "save_revision_files", "stream_upload_to_tempfile"]
