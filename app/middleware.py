# app/middleware.py

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Header, HTTPException, Request
from fastapi.security import APIKeyHeader

from secrets import compare_digest

from .config import DEBUG, VALID_API_KEY_HASHES, hash_api_key

logger = logging.getLogger(__name__)

# API Key scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """
    Preveri veljavnost API ključa.

    Args:
        x_api_key: API ključ iz HTTP headerja

    Returns:
        Veljaven API ključ

    Raises:
        HTTPException(401): Če API ključ ni veljaven ali manjka
    """
    # V DEBUG načinu dovoli dostop brez API ključa (SAMO za razvoj!)
    # OPOMBA: startup_event() v main.py preprečuje DEBUG=true v produkciji
    if DEBUG and not x_api_key:
        logger.warning(
            "⚠️ DEBUG mode: Zahteva brez API ključa je dovoljena. "
            "To je VARNOSTNO TVEGANJE - uporabite samo v razvojnem okolju!"
        )
        return "debug_bypass"

    if not x_api_key:
        logger.warning("Zahteva brez API ključa zavrnjena")
        raise HTTPException(
            status_code=401,
            detail="API ključ manjka. Dodajte 'X-API-Key' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    api_key_hash = hash_api_key(x_api_key)
    if not any(compare_digest(api_key_hash, stored) for stored in VALID_API_KEY_HASHES):
        # NE logiraj nobenih delov API ključa - samo hash za debugging
        key_hash_prefix = api_key_hash[:12]
        logger.warning(
            f"Neveljaven API ključ poskus (hash prefix: {key_hash_prefix})"
        )
        raise HTTPException(
            status_code=401,
            detail="Neveljaven API ključ",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return x_api_key


async def log_requests_middleware(request: Request, call_next):
    """
    Middleware za logiranje vseh zahtevkov.

    Zabeleži:
    - Pot zahtevka
    - Metodo
    - IP naslov
    - Trajanje obdelave
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Zahteva: {request.method} {request.url.path} od {client_ip}")

    try:
        response = await call_next(request)
        logger.info(
            f"Odgovor: {request.method} {request.url.path} -> {response.status_code}"
        )
        return response
    except Exception as exc:
        logger.error(
            f"Napaka pri obdelavi: {request.method} {request.url.path}: {exc}",
            exc_info=True
        )
        raise


__all__ = ["verify_api_key", "api_key_header", "log_requests_middleware"]
