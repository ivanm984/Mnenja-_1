# app/main.py (posodobljena verzija)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import db_manager
from .routes import router
from .logging_config import setup_logging # SPREMEMBA: Uvozimo funkcijo
from .config import FRONTEND_DIST_DIR

app = FastAPI(title="Avtomatski API za Skladnost", version="21.0.0")

# SPREMEMBA: Kličemo funkcijo za nastavitev beleženja
setup_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

assets_path = FRONTEND_DIST_DIR / "assets"
if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

@app.on_event("startup")
async def startup_event():
    await db_manager.init_db()

app.include_router(router)