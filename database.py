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
                CREATE TABLE IF NOT EXISTS gurs_locations (
                    session_id TEXT PRIMARY KEY,
                    parcel_number TEXT NOT NULL,
                    cadastral_municipality TEXT NOT NULL,
                    centroid_lat REAL,
                    centroid_lon REAL,
                    geometry_geojson TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
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
            await db.execute("DELETE FROM gurs_locations WHERE session_id = ?", (session_id,))
            await db.commit()

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

    async def upsert_gurs_location(
        self,
        session_id: str,
        parcel_number: str,
        cadastral_municipality: str,
        centroid_lat: float | None,
        centroid_lon: float | None,
        geometry: Dict[str, Any] | None,
    ) -> None:
        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT INTO gurs_locations (
                    session_id, parcel_number, cadastral_municipality,
                    centroid_lat, centroid_lon, geometry_geojson, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    parcel_number=excluded.parcel_number,
                    cadastral_municipality=excluded.cadastral_municipality,
                    centroid_lat=excluded.centroid_lat,
                    centroid_lon=excluded.centroid_lon,
                    geometry_geojson=excluded.geometry_geojson,
                    updated_at=excluded.updated_at;
                """,
                (
                    session_id,
                    parcel_number,
                    cadastral_municipality,
                    centroid_lat,
                    centroid_lon,
                    json.dumps(geometry) if geometry is not None else None,
                    datetime.utcnow(),
                ),
            )
            await db.commit()

    async def fetch_gurs_location(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT parcel_number, cadastral_municipality, centroid_lat, centroid_lon, geometry_geojson, updated_at FROM gurs_locations WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            geometry_raw = row["geometry_geojson"]
            geometry = json.loads(geometry_raw) if geometry_raw else None
            return {
                "parcel_number": row["parcel_number"],
                "cadastral_municipality": row["cadastral_municipality"],
                "centroid": {
                    "lat": row["centroid_lat"],
                    "lon": row["centroid_lon"],
                },
                "geometry": geometry,
                "updated_at": row["updated_at"],
            }

    async def delete_gurs_location(self, session_id: str) -> None:
        async with self._get_connection() as db:
            await db.execute("DELETE FROM gurs_locations WHERE session_id = ?", (session_id,))
            await db.commit()


# Ustvarimo eno samo instanco, ki jo bo uporabljala celotna aplikacija.
db_manager = DatabaseManager()

__all__ = ["db_manager", "compute_session_summary"]