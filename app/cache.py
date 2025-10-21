# app/cache.py (NOVA DATOTEKA)

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from .config import REDIS_URL, SESSION_TTL_SECONDS

# Ustvarimo eno samo povezavo, ki jo bo uporabljala celotna aplikacija.
# To je veliko bolj učinkovito kot ustvarjanje nove povezave ob vsakem klicu.
pool = ConnectionPool.from_url(REDIS_URL, decode_responses=True)


class CacheManager:
    """Asinhroni upravitelj za shranjevanje in pridobivanje podatkov iz Redisa."""

    def __init__(self, connection_pool: ConnectionPool, default_ttl: int = SESSION_TTL_SECONDS):
        """
        Args:
            connection_pool: Povezava do Redis strežnika.
            default_ttl: Privzeti čas veljavnosti ključa v sekundah.
        """
        self.client = redis.Redis(connection_pool=connection_pool)
        self.ttl = default_ttl

    async def store_session_data(self, session_id: str, data: Dict[str, Any]):
        """Shrani podatke seje v Redis kot JSON niz."""
        key = f"session:{session_id}"
        value = json.dumps(data)
        # `setex` postavi ključ z določenim časom veljavnosti (time-to-live).
        await self.client.setex(key, self.ttl, value)

    async def retrieve_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Pridobi in deserializira podatke seje iz Redisa."""
        key = f"session:{session_id}"
        data_str = await self.client.get(key)
        if data_str:
            return json.loads(data_str)
        return None

    async def delete_session_data(self, session_id: str):
        """Izbriše podatke seje iz Redisa."""
        key = f"session:{session_id}"
        await self.client.delete(key)


# Ustvarimo eno samo instanco, ki jo bo uporabljala celotna aplikacija.
cache_manager = CacheManager(connection_pool=pool)

__all__ = ["cache_manager"]