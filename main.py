# app/main.py (posodobljena verzija)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import db_manager
from .routes import router
from .logging_config import setup_logging # SPREMEMBA: Uvozimo funkcijo

app = FastAPI(title="Avtomatski API za Skladnost", version="21.0.0")

# SPREMEMBA: Kličemo funkcijo za nastavitev beleženja
setup_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await db_manager.init_db()

app.include_router(router)