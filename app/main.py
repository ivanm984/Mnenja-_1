# app/main.py (posodobljena verzija z varnostnimi izboljšavami)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .database import db_manager
from .routes import router
from .gurs_routes import router as gurs_router
from .logging_config import setup_logging
from .config import PROJECT_ROOT, ALLOWED_ORIGINS, RATE_LIMIT_PER_MINUTE
from .middleware import log_requests_middleware

# Inicializacija aplikacije
app = FastAPI(
    title="Avtomatski API za Skladnost",
    version="22.0.0",
    description="API za avtomatsko preverjanje skladnosti gradbenih projektov z občinskimi predpisi",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Nastavitev logiranja
setup_logging()

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT_PER_MINUTE}/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware - VARNO konfigurirano
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Iz .env konfiguracije
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],  # Samo potrebne metode
    allow_headers=["*"],
)

# Request logging middleware
app.middleware("http")(log_requests_middleware)

# NOVO: Mount static files za JavaScript in CSS
static_path = PROJECT_ROOT / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.on_event("startup")
async def startup_event():
    """Inicializacija ob zagonu aplikacije."""
    await db_manager.init_db()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup ob zaustavitvi aplikacije."""
    # Zapremo Redis povezavo
    from .cache import cache_manager
    if hasattr(cache_manager, 'client'):
        await cache_manager.client.close()

# Include routers
app.include_router(router)
app.include_router(gurs_router)