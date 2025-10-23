# app/temp_storage.py (NOVA DATOTEKA)

import asyncio
import io
import logging
import re
import shutil
from pathlib import Path
from typing import List

import aiofiles
from fastapi import HTTPException
from PIL import Image

from .config import TEMP_STORAGE_PATH
from .security import validate_session_id, validate_path_safety

logger = logging.getLogger(__name__)

async def save_images_for_session(session_id: str, images: List[Image.Image]) -> List[str]:
    """Asinhrono shrani PIL slike na disk in vrne seznam njihovih poti."""
    # VARNOSTNO: Validiraj session_id format
    try:
        validate_session_id(session_id)
    except ValueError as e:
        logger.error(f"Neveljaven session_id: {e}")
        raise HTTPException(status_code=400, detail=f"Neveljaven session_id: {e}")

    session_dir = TEMP_STORAGE_PATH / session_id

    # VARNOSTNO: Preveri path traversal
    try:
        validate_path_safety(session_dir, TEMP_STORAGE_PATH)
    except ValueError as e:
        logger.error(f"Path traversal poskus zaznan: {e}")
        raise HTTPException(status_code=400, detail="Neveljaven session_id")

    session_dir.mkdir(exist_ok=True, parents=True)

    existing_indices = []
    for path in session_dir.glob("image_*.png"):
        match = re.search(r"image_(\d+)\.png$", path.name)
        if match:
            try:
                existing_indices.append(int(match.group(1)))
            except ValueError:
                continue
    start_index = max(existing_indices, default=0)

    saved_paths = []
    tasks = []

    for offset, img in enumerate(images, start=1):
        img_path = session_dir / f"image_{start_index + offset}.png"
        tasks.append(_save_single_image(img, img_path))
        saved_paths.append(str(img_path))
    
    await asyncio.gather(*tasks)
    logger.info(f"[{session_id}] Shranjenih {len(images)} slik v mapo {session_dir}")
    return saved_paths

async def _save_single_image(img: Image.Image, path: Path):
    """Pomožna funkcija za shranjevanje ene slike."""
    with io.BytesIO() as buffer:
        img.save(buffer, format="PNG")
        content = buffer.getvalue()
    
    async with aiofiles.open(path, "wb") as f:
        await f.write(content)

async def load_images_from_paths(image_paths: List[str]) -> List[Image.Image]:
    """Asinhrono naloži slike z diska na podlagi seznama poti."""
    tasks = [asyncio.to_thread(Image.open, path) for path in image_paths]
    images = await asyncio.gather(*tasks)
    return images

async def cleanup_session_storage(session_id: str):
    """Počisti začasno mapo s slikami za določeno sejo."""
    # VARNOSTNO: Validiraj session_id format
    try:
        validate_session_id(session_id)
    except ValueError as e:
        logger.warning(f"Poskus čiščenja z neveljavnim session_id: {e}")
        return  # Tiho prekini, ne raise exception

    session_dir = TEMP_STORAGE_PATH / session_id

    # VARNOSTNO: Preveri path traversal
    try:
        validate_path_safety(session_dir, TEMP_STORAGE_PATH)
    except ValueError as e:
        logger.error(f"❌ Path traversal poskus pri čiščenju: {e}")
        return  # Tiho prekini, ne izbriši nič

    if session_dir.exists():
        try:
            # shutil.rmtree je blokirajoča operacija, zato jo poženemo v ločeni niti
            await asyncio.to_thread(shutil.rmtree, session_dir)
            logger.info(f"[{session_id}] Počiščena začasna mapa: {session_dir}")
        except Exception as e:
            logger.error(f"[{session_id}] Napaka pri čiščenju mape {session_dir}: {e}")