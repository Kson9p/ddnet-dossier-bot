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
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS source_bot_verifications (
                user_id INTEGER PRIMARY KEY,
                verified_at INTEGER NOT NULL
            )
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_challenges (
                nonce TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS dossier_votes (
                dossier_id INTEGER NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
                voter_key TEXT NOT NULL,
                score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 7),
                created_at INTEGER NOT NULL,
                changed_at INTEGER,
                change_count INTEGER NOT NULL DEFAULT 0 CHECK(change_count BETWEEN 0 AND 1),
                voter_telegram_id INTEGER,
                voter_username TEXT,
                voter_display_name TEXT,
                PRIMARY KEY(dossier_id, voter_key)
            )
        """)
        vote_columns = {
            row["name"]
            for row in await (await self.conn.execute("PRAGMA table_info(dossier_votes)")).fetchall()
        }
        for column, definition in (
            ("voter_telegram_id", "INTEGER"),
            ("voter_username", "TEXT"),
            ("voter_display_name", "TEXT"),
        ):
            if column not in vote_columns:
                await self.conn.execute(
                    f"ALTER TABLE dossier_votes ADD COLUMN {column} {definition}"
                )
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    def _db(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("Dossier database is not open")
        return self.conn

    async def issue_verification_challenge(self, user_id: int, nonce: str, created_at: int) -> None:
        await self._db().execute("DELETE FROM verification_challenges WHERE created_at < ?", (created_at - 600,))
        await self._db().execute(
            "INSERT OR REPLACE INTO verification_challenges(nonce,user_id,created_at) VALUES(?,?,?)",
            (nonce, user_id, created_at),
        )
        await self._db().commit()

    async def accept_source_bot_proof(self, user_id: int, nonce: str, issued_at: int) -> bool:
        cursor = await self._db().execute(
            "SELECT created_at FROM verification_challenges WHERE nonce=? AND user_id=?",
            (nonce, user_id),
        )
        row = await cursor.fetchone()
        if not row or abs(int(row["created_at"]) - issued_at) > 600:
            return False
        await self._db().execute("DELETE FROM verification_challenges WHERE nonce=?", (nonce,))
        await self._db().execute(
            "INSERT OR REPLACE INTO source_bot_verifications(user_id,verified_at) VALUES(?,?)",
            (user_id, int(time.time())),
        )
        await self._db().commit()
        return True

    async def has_source_bot_verification(self, user_id: int, *, max_age: int = 2_592_000) -> bool:
        cursor = await self._db().execute(
            "SELECT verified_at FROM source_bot_verifications WHERE user_id=?", (user_id,)
        )
        row = await cursor.fetchone()
        return bool(row and int(row["verified_at"]) >= int(time.time()) - max_age)

    async def get_vote_summary(self, dossier_id: int, voter_key: str | None = None) -> dict:
        cursor = await self._db().execute(
            "SELECT COUNT(*) AS vote_count, AVG(score) AS average FROM dossier_votes WHERE dossier_id=?",
            (dossier_id,),
        )
        aggregate = await cursor.fetchone()
        own_vote = None
        if voter_key:
            cursor = await self._db().execute(
                "SELECT score, created_at, change_count FROM dossier_votes WHERE dossier_id=? AND voter_key=?",
                (dossier_id, voter_key),
            )
            own_vote = await cursor.fetchone()
        created_at = int(own_vote["created_at"]) if own_vote else None
        change_count = int(own_vote["change_count"]) if own_vote else 0
        return {
            "count": int(aggregate["vote_count"] or 0),
            "average": round(float(aggregate["average"]), 2) if aggregate["average"] is not None else None,
            "myScore": int(own_vote["score"]) if own_vote else None,
            "changeAt": created_at + 7 * 24 * 60 * 60 if created_at is not None and change_count == 0 else None,
            "changeUsed": change_count >= 1,
        }

    async def update_voter_username(self, dossier_id: int, telegram_user_id: int, username: str) -> None:
        await self._db().execute(
            "UPDATE dossier_votes SET voter_username=? WHERE dossier_id=? AND voter_telegram_id=?",
            (username, dossier_id, telegram_user_id),
        )
        await self._db().commit()

    async def get_vote_breakdown(self, dossier_id: int) -> list[dict]:
        cursor = await self._db().execute(
            "SELECT score, COUNT(*) AS vote_count FROM dossier_votes WHERE dossier_id=? GROUP BY score",
            (dossier_id,),
        )
        counts = {int(row["score"]): int(row["vote_count"]) for row in await cursor.fetchall()}
        cursor = await self._db().execute(
            "SELECT score, voter_telegram_id, voter_username, voter_display_name, created_at "
            "FROM dossier_votes WHERE dossier_id=? AND voter_telegram_id IS NOT NULL "
            "ORDER BY created_at DESC",
            (dossier_id,),
        )
        voters: dict[int, list[dict]] = {score: [] for score in range(1, 8)}
        for row in await cursor.fetchall():
            voters[int(row["score"])].append({
                "userId": int(row["voter_telegram_id"]),
                "username": row["voter_username"],
                "displayName": row["voter_display_name"] or "Пользователь Telegram",
                "createdAt": int(row["created_at"]),
            })
        return [
            {"score": score, "count": counts.get(score, 0), "voters": voters[score]}
            for score in range(7, 0, -1)
        ]

    async def cast_vote(
        self,
        dossier_id: int,
        voter_key: str,
        score: int,
        *,
        telegram_user_id: int | None = None,
        username: str | None = None,
        display_name: str | None = None,
        now: int | None = None,
    ) -> str:
        if type(score) is not int or not 1 <= score <= 7:
            raise ValueError("Vote score must be an integer between 1 and 7")
        timestamp = int(time.time()) if now is None else now
        connection = self._db()
        await connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = await connection.execute(
                "SELECT score, created_at, change_count FROM dossier_votes WHERE dossier_id=? AND voter_key=?",
                (dossier_id, voter_key),
            )
            existing = await cursor.fetchone()
            if existing is None:
                await connection.execute(
                    "INSERT INTO dossier_votes("
                    "dossier_id,voter_key,score,created_at,voter_telegram_id,voter_username,voter_display_name"
                    ") VALUES(?,?,?,?,?,?,?)",
                    (dossier_id, voter_key, score, timestamp, telegram_user_id, username, display_name),
                )
                outcome = "created"
            elif int(existing["score"]) == score:
                outcome = "same"
            elif int(existing["change_count"]) >= 1:
                outcome = "change_used"
            elif timestamp < int(existing["created_at"]) + 7 * 24 * 60 * 60:
                outcome = "too_early"
            else:
                await connection.execute(
                    "UPDATE dossier_votes SET score=?, changed_at=?, change_count=1 WHERE dossier_id=? AND voter_key=?",
                    (score, timestamp, dossier_id, voter_key),
                )
                outcome = "changed"
            if telegram_user_id is not None:
                await connection.execute(
                    "UPDATE dossier_votes SET voter_telegram_id=?, voter_username=?, voter_display_name=? "
                    "WHERE dossier_id=? AND voter_key=?",
                    (telegram_user_id, username, display_name, dossier_id, voter_key),
                )
            await connection.commit()
            return outcome
        except BaseException:
            await connection.rollback()
            raise

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
        elif sort in {"name_asc", "name_desc"}:
            rows.sort(
                key=lambda row: (row["nickname"].casefold(), int(row["id"])),
                reverse=sort == "name_desc",
            )
        elif sort in {"rating_asc", "rating_desc"}:
            cursor = await self._db().execute(
                "SELECT dossier_id, AVG(score) AS average FROM dossier_votes GROUP BY dossier_id"
            )
            averages = {
                int(row["dossier_id"]): float(row["average"])
                for row in await cursor.fetchall()
            }
            if sort == "rating_desc":
                rows.sort(key=lambda row: (
                    averages.get(int(row["id"])) is None,
                    -averages.get(int(row["id"]), 0),
                    row["nickname"].casefold(),
                ))
            else:
                # Profiles without votes have no established score, so treat them
                # as zero and put them first in the low-to-high order.
                rows.sort(key=lambda row: (
                    averages.get(int(row["id"])) is not None,
                    averages.get(int(row["id"]), 0),
                    row["nickname"].casefold(),
                ))
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
