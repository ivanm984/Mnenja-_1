# app/database.py (POPRAVLJENA vsebina)

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

from .config import DEFAULT_SQLITE_PATH


def compute_session_summary(data: Dict[str, Any]) -> str:
    """Generira kratek povzetek analize na podlagi podatkov."""
    try:
        results = data.get("resultsMap", {})
        if not results:
            return "Analiza še ni bila izvedena."
        
        total = len(results)
        neskladnih = sum(1 for res in results.values() if "nesklad" in str(res.get("skladnost", "")).lower())

        if neskladnih > 0:
            return f"Ugotovljenih {neskladnih} od {total} neskladnih zahtev."
        return f"Vseh {total} zahtev je skladnih."
    except Exception:
        return "Povzetek ni na voljo."


class DatabaseManager:
    """Asinhroni upravitelj za interakcijo s SQLite bazo podatkov."""

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or DEFAULT_SQLITE_PATH)

    def _get_connection(self) -> aiosqlite.Connection:
        """Pripravi asinhrono povezavo z bazo."""
        # Vrača coroutine, ki ga bo `async with` pravilno obravnaval
        return aiosqlite.connect(self.db_path)

    async def init_db(self):
        """Inicializira shemo baze podatkov, če tabele ne obstajajo."""
        # SPREMEMBA: Odstranjen `await` pred klicem `self._get_connection()`
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, project_name TEXT, summary TEXT, data JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, requirement_id TEXT,
                    note TEXT, filenames JSON, file_paths JSON, mime_types JSON,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS map_states (
                    session_id TEXT PRIMARY KEY,
                    center_lon REAL NOT NULL,
                    center_lat REAL NOT NULL,
                    zoom INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.commit()

    async def upsert_session(self, session_id: str, project_name: str, summary: str, data: Dict[str, Any]):
        """Shrani ali posodobi sejo v bazi."""
        # SPREMEMBA: Odstranjen `await`
        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT INTO sessions (session_id, project_name, summary, data, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    project_name=excluded.project_name, summary=excluded.summary,
                    data=excluded.data, updated_at=excluded.updated_at;
                """,
                (session_id, project_name, summary, json.dumps(data), datetime.utcnow()),
            )
            await db.commit()

    async def fetch_sessions(self) -> List[aiosqlite.Row]:
        """Pridobi vse shranjene seje, najnovejše najprej."""
        # SPREMEMBA: Odstranjen `await`
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT session_id, project_name, summary, updated_at FROM sessions ORDER BY updated_at DESC")
            return await cursor.fetchall()

    async def fetch_session(self, session_id: str) -> Optional[Dict]:
        """Pridobi eno sejo po njenem ID-ju."""
        # SPREMEMBA: Odstranjen `await`
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            record = await cursor.fetchone()
            if record:
                data_dict = dict(record)
                data_dict['data'] = json.loads(data_dict['data'])
                return data_dict
            return None

    async def delete_session(self, session_id: str):
        """Izbriše sejo in vse povezane popravke iz baze."""
        # SPREMEMBA: Odstranjen `await`
        async with self._get_connection() as db:
            await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM revisions WHERE session_id = ?", (session_id,))
            await db.commit()

    async def save_map_state(self, session_id: str, center_lon: float, center_lat: float, zoom: int):
        """Shrani ali posodobi zadnjo lokacijo zemljevida za sejo."""
        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT INTO map_states (session_id, center_lon, center_lat, zoom, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    center_lon=excluded.center_lon,
                    center_lat=excluded.center_lat,
                    zoom=excluded.zoom,
                    updated_at=excluded.updated_at;
                """,
                (session_id, center_lon, center_lat, zoom, datetime.utcnow()),
            )
            await db.commit()

    async def fetch_map_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Vrne shranjeno lokacijo zemljevida za sejo, če obstaja."""
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT center_lon, center_lat, zoom, updated_at FROM map_states WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "center_lon": row["center_lon"],
                    "center_lat": row["center_lat"],
                    "zoom": row["zoom"],
                    "updated_at": row["updated_at"],
                }
            return None

    async def record_revision(self, session_id: str, filenames: List[str], file_paths: List[str], requirement_id: str | None = None, note: str | None = None, mime_types: List[str] | None = None) -> Dict:
        """Zabeleži nov popravek v bazo."""
        uploaded_at = datetime.utcnow()
        # SPREMEMBA: Odstranjen `await`
        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT INTO revisions (session_id, requirement_id, note, filenames, file_paths, mime_types, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, requirement_id, note, json.dumps(filenames), json.dumps(file_paths), json.dumps(mime_types or []), uploaded_at),
            )
            await db.commit()
        return {"uploaded_at": uploaded_at.isoformat()}
    
    async def fetch_revisions(self, session_id: str) -> List[Dict]:
        """Pridobi vse popravke za določeno sejo."""
        # SPREMEMBA: Odstranjen `await`
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM revisions WHERE session_id = ? ORDER BY uploaded_at DESC", (session_id,))
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data['filenames'] = json.loads(data.get('filenames', '[]'))
                data['file_paths'] = json.loads(data.get('file_paths', '[]'))
                results.append(data)
            return results


# Ustvarimo eno samo instanco, ki jo bo uporabljala celotna aplikacija.
db_manager = DatabaseManager()

__all__ = ["db_manager", "compute_session_summary"]