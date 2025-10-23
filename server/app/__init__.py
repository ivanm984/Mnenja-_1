"""Server application package for GURS integration."""

from fastapi import FastAPI

from .gurs.proxy import router as gurs_proxy_router
from .gurs.routes import router as gurs_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="GURS Integration Service")
    app.include_router(gurs_proxy_router)
    app.include_router(gurs_router)
    return app


__all__ = ["create_app"]
