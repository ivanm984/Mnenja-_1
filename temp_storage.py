# app/temp_storage.py (NOVA DATOTEKA)

import asyncio
import io
import logging
import shutil
from pathlib import Path
from typing import List

import aiofiles
from PIL import Image

from .config import TEMP_STORAGE_PATH

logger = logging.getLogger(__name__)

async def save_images_for_session(session_id: str, images: List[Image.Image]) -> List[str]:
    """Asinhrono shrani PIL slike na disk in vrne seznam njihovih poti."""
    session_dir = TEMP_STORAGE_PATH / session_id
    session_dir.mkdir(exist_ok=True, parents=True)
    
    saved_paths = []
    tasks = []

    for i, img in enumerate(images):
        img_path = session_dir / f"image_{i+1}.png"
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
    session_dir = TEMP_STORAGE_PATH / session_id
    if session_dir.exists():
        try:
            # shutil.rmtree je blokirajoča operacija, zato jo poženemo v ločeni niti
            await asyncio.to_thread(shutil.rmtree, session_dir)
            logger.info(f"[{session_id}] Počiščena začasna mapa: {session_dir}")
        except Exception as e:
            logger.error(f"[{session_id}] Napaka pri čiščenju mape {session_dir}: {e}")