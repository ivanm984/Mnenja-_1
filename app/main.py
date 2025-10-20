# app/main.py (posodobljena verzija z GURS routing)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import db_manager
from .routes import router
from .gurs_routes import router as gurs_router  # NOVO: GURS routing
from .logging_config import setup_logging
from .config import PROJECT_ROOT

app = FastAPI(title="Avtomatski API za Skladnost", version="22.0.0")

# Nastavitev logiranja
setup_logging()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# NOVO: Mount static files za JavaScript in CSS
static_path = PROJECT_ROOT / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.on_event("startup")
async def startup_event():
    await db_manager.init_db()

# Include routers
app.include_router(router)
app.include_router(gurs_router)  # NOVO: GURS endpoints