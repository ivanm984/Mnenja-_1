"""FastAPI application entrypoint for GURS integration."""

from fastapi import FastAPI

from .gurs.proxy import router as gurs_proxy_router
from .gurs.routes import router as gurs_router

app = FastAPI(title="GURS Integration Service")


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Simple health-check endpoint for the service itself."""
    return {"status": "ok"}


app.include_router(gurs_proxy_router)
app.include_router(gurs_router)
