from __future__ import annotations

import json
import os
import time
from pathlib import Path

import aiosqlite


class DossierStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(self.path.parent, 0o700)
        self.conn = await aiosqlite.connect(self.path)
        if os.name != "nt":
            os.chmod(self.path, 0o600)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS dossiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                gender TEXT NOT NULL,
                nickname TEXT NOT NULL,
                description TEXT NOT NULL,
                media_json TEXT NOT NULL DEFAULT '[]',
                stats_text TEXT NOT NULL,
                admin_messages_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL
            )
        """)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    def _db(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("Dossier database is not open")
        return self.conn

    async def add(self, user_id: int, draft: dict) -> int:
        cursor = await self._db().execute(
            "INSERT INTO dossiers(user_id,gender,nickname,description,media_json,stats_text,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, draft["gender"], draft["nickname"], draft["description"],
             json.dumps(draft.get("media", [])), draft.get("stats_text", ""), int(time.time())),
        )
        await self._db().commit()
        return int(cursor.lastrowid)

    async def get(self, dossier_id: int) -> dict | None:
        cursor = await self._db().execute("SELECT * FROM dossiers WHERE id=?", (dossier_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_approved(self, *, query: str = "", gender: str = "", sort: str = "default", page: int = 1, page_size: int = 6) -> tuple[list[dict], int]:
        cursor = await self._db().execute(
            "SELECT * FROM dossiers WHERE status='approved' ORDER BY created_at DESC, id DESC"
        )
        rows = [dict(row) for row in await cursor.fetchall()]
        needle = query.strip().casefold()
        if needle:
            rows = [row for row in rows if needle in row["nickname"].casefold()]
        if gender in {"boy", "girl"}:
            rows = [row for row in rows if row.get("gender") == gender]
        if sort == "points":
            import re
            def points(row: dict) -> int:
                match = re.search(r"DDRaceNetwork:\s*(\d+)\s+очков", row.get("stats_text", ""), re.IGNORECASE)
                return int(match.group(1)) if match else 0
            rows.sort(key=points, reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start:start + page_size], total

    async def set_messages(self, dossier_id: int, message_ids: list[int]) -> None:
        await self._db().execute(
            "UPDATE dossiers SET admin_messages_json=? WHERE id=?",
            (json.dumps(message_ids), dossier_id),
        )
        await self._db().commit()

    async def set_status(self, dossier_id: int, status: str) -> None:
        await self._db().execute("UPDATE dossiers SET status=? WHERE id=?", (status, dossier_id))
        await self._db().commit()

    async def delete(self, dossier_id: int, user_id: int | None = None) -> bool:
        if user_id is None:
            cursor = await self._db().execute("DELETE FROM dossiers WHERE id=?", (dossier_id,))
        else:
            cursor = await self._db().execute(
                "DELETE FROM dossiers WHERE id=? AND user_id=?", (dossier_id, user_id)
            )
        await self._db().commit()
        return cursor.rowcount > 0
