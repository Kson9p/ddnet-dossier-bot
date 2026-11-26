"""Асинхронная работа с SQLite.

Хранятся только служебные данные и короткие текстовые превью сообщений,
необходимые для истории. Медиафайлы в базу и на диск не сохраняются.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import aiosqlite

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DatabaseError(RuntimeError):
    """Ошибка доступа к базе данных без раскрытия деталей пользователю."""


def _db_guard(
    method: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    @functools.wraps(method)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await method(*args, **kwargs)
        except aiosqlite.Error as exc:
            database = args[0] if args else None
            connection = getattr(database, "_conn", None)
            if connection is not None:
                with contextlib.suppress(aiosqlite.Error):
                    await connection.rollback()
            logger.error("Ошибка SQLite: %s", type(exc).__name__)
            raise DatabaseError(
                "Не удалось выполнить операцию с базой данных."
            ) from exc

    return wrapper


@dataclass(frozen=True, slots=True)
class DialogRecord:
    id: int
    user_id: int
    display_name: str
    username: str | None
    first_seen: int
    last_seen: int
    messages_count: int
    is_blocked: bool
    blocked_at: int | None
    blocked_reason: str | None
    status: str
    unread_count: int
    created_at: int
    updated_at: int
    last_message_at: int | None


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: int
    dialog_id: int
    direction: str
    kind: str
    content: str | None
    created_at: int


@dataclass(frozen=True, slots=True)
class StatsRecord:
    new_messages: int
    active_dialogs: int
    total_users: int
    blocked_users: int


DIALOG_SELECT = """
SELECT
    d.id AS id,
    d.user_id AS user_id,
    u.display_name AS display_name,
    u.username AS username,
    u.first_seen AS first_seen,
    u.last_seen AS last_seen,
    u.messages_count AS messages_count,
    u.is_blocked AS is_blocked,
    u.blocked_at AS blocked_at,
    u.blocked_reason AS blocked_reason,
    d.status AS status,
    d.unread_count AS unread_count,
    d.created_at AS created_at,
    d.updated_at AS updated_at,
    d.last_message_at AS last_message_at
FROM dialogs AS d
JOIN users AS u ON u.telegram_id = d.user_id
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    username TEXT,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    is_blocked INTEGER NOT NULL DEFAULT 0,
    blocked_at INTEGER,
    blocked_reason TEXT,
    messages_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dialogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    last_message_at INTEGER,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    unread_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dialog_id INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    kind TEXT NOT NULL,
    content TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (dialog_id) REFERENCES dialogs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_dialog_id
    ON messages(dialog_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_messages_created_at
    ON messages(created_at);

CREATE TABLE IF NOT EXISTS owner_messages (
    owner_chat_id INTEGER NOT NULL,
    owner_message_id INTEGER NOT NULL,
    dialog_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (owner_chat_id, owner_message_id),
    FOREIGN KEY (dialog_id) REFERENCES dialogs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_owner_messages_created_at
    ON owner_messages(created_at);

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id INTEGER PRIMARY KEY,
    processed_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_processed_updates_at
    ON processed_updates(processed_at);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._updates_since_cleanup = 0

    @property
    def path(self) -> Path:
        return self._path

    @_db_guard
    async def connect(self) -> None:
        if self._conn is not None:
            return
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(
            str(self._path),
            timeout=30.0,
        )
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 10000")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self._conn.commit()

    @_db_guard
    async def initialize(self) -> None:
        async with self._lock:
            conn = self._require_conn()
            await conn.executescript(SCHEMA)
            await conn.execute("PRAGMA user_version = 1")
            await conn.commit()

    @_db_guard
    async def close(self) -> None:
        async with self._lock:
            if self._conn is None:
                return
            with contextlib.suppress(aiosqlite.Error):
                await self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                await self._conn.commit()
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise DatabaseError("База данных не подключена.")
        return self._conn

    @staticmethod
    def _row_to_dialog(row: aiosqlite.Row) -> DialogRecord:
        return DialogRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            display_name=str(row["display_name"] or ""),
            username=row["username"],
            first_seen=int(row["first_seen"]),
            last_seen=int(row["last_seen"]),
            messages_count=int(row["messages_count"]),
            is_blocked=bool(row["is_blocked"]),
            blocked_at=row["blocked_at"],
            blocked_reason=row["blocked_reason"],
            status=str(row["status"]),
            unread_count=int(row["unread_count"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            last_message_at=row["last_message_at"],
        )

    @staticmethod
    def _row_to_message(row: aiosqlite.Row) -> MessageRecord:
        return MessageRecord(
            id=int(row["id"]),
            dialog_id=int(row["dialog_id"]),
            direction=str(row["direction"]),
            kind=str(row["kind"]),
            content=row["content"],
            created_at=int(row["created_at"]),
        )

    async def _fetch_dialog_locked(self, dialog_id: int) -> DialogRecord | None:
        conn = self._require_conn()
        cursor = await conn.execute(DIALOG_SELECT + " WHERE d.id = ?", (dialog_id,))
        row = await cursor.fetchone()
        return self._row_to_dialog(row) if row is not None else None

    @_db_guard
    async def get_or_create_dialog(
        self,
        telegram_id: int,
        display_name: str,
        username: str | None,
        *,
        now: int | None = None,
    ) -> DialogRecord:
        timestamp = int(time.time()) if now is None else now
        clean_name = (display_name or "").strip()[:128]
        clean_username = (username or "").strip().lstrip("@")[:64] or None

        async with self._lock:
            conn = self._require_conn()
            await conn.execute(
                """
                INSERT INTO users (
                    telegram_id, display_name, username, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    username = excluded.username,
                    last_seen = excluded.last_seen
                """,
                (telegram_id, clean_name, clean_username, timestamp, timestamp),
            )
            await conn.execute(
                """
                INSERT INTO dialogs (user_id, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (telegram_id, timestamp, timestamp),
            )
            await conn.commit()

            cursor = await conn.execute(
                DIALOG_SELECT + " WHERE d.user_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise DatabaseError("Не удалось создать диалог.")
            return self._row_to_dialog(row)

    @_db_guard
    async def get_dialog(self, dialog_id: int) -> DialogRecord | None:
        async with self._lock:
            return await self._fetch_dialog_locked(dialog_id)

    @_db_guard
    async def get_dialog_by_user(self, telegram_id: int) -> DialogRecord | None:
        async with self._lock:
            conn = self._require_conn()
            cursor = await conn.execute(
                DIALOG_SELECT + " WHERE d.user_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            return self._row_to_dialog(row) if row is not None else None

    @_db_guard
    async def record_incoming(
        self,
        dialog_id: int,
        kind: str,
        content: str | None,
        *,
        count: int = 1,
        now: int | None = None,
    ) -> MessageRecord:
        timestamp = int(time.time()) if now is None else now
        safe_count = max(1, int(count))
        async with self._lock:
            conn = self._require_conn()
            cursor = await conn.execute(
                "SELECT user_id FROM dialogs WHERE id = ?",
                (dialog_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise DatabaseError("Диалог не найден.")
            user_id = int(row["user_id"])

            await conn.execute(
                """
                UPDATE users
                SET messages_count = messages_count + ?, last_seen = ?
                WHERE telegram_id = ?
                """,
                (safe_count, timestamp, user_id),
            )
            await conn.execute(
                """
                UPDATE dialogs
                SET unread_count = unread_count + ?,
                    status = 'open',
                    updated_at = ?,
                    last_message_at = ?
                WHERE id = ?
                """,
                (safe_count, timestamp, timestamp, dialog_id),
            )
            cursor = await conn.execute(
                """
                INSERT INTO messages (dialog_id, direction, kind, content, created_at)
                VALUES (?, 'in', ?, ?, ?)
                """,
                (dialog_id, kind[:32], content, timestamp),
            )
            message_id = cursor.lastrowid
            await conn.commit()
            if message_id is None:
                raise DatabaseError("Не удалось сохранить сообщение.")
            return MessageRecord(
                id=int(message_id),
                dialog_id=dialog_id,
                direction="in",
                kind=kind[:32],
                content=content,
                created_at=timestamp,
            )

    @_db_guard
    async def record_outgoing(
        self,
        dialog_id: int,
        kind: str,
        content: str | None,
        *,
        now: int | None = None,
    ) -> MessageRecord:
        timestamp = int(time.time()) if now is None else now
        async with self._lock:
            conn = self._require_conn()
            await conn.execute(
                """
                UPDATE dialogs
                SET unread_count = 0, updated_at = ?, last_message_at = ?
                WHERE id = ?
                """,
                (timestamp, timestamp, dialog_id),
            )
            cursor = await conn.execute(
                """
                INSERT INTO messages (dialog_id, direction, kind, content, created_at)
                VALUES (?, 'out', ?, ?, ?)
                """,
                (dialog_id, kind[:32], content, timestamp),
            )
            message_id = cursor.lastrowid
            await conn.commit()
            if message_id is None:
                raise DatabaseError("Не удалось сохранить ответ.")
            return MessageRecord(
                id=int(message_id),
                dialog_id=dialog_id,
                direction="out",
                kind=kind[:32],
                content=content,
                created_at=timestamp,
            )

    @_db_guard
    async def mark_read(self, dialog_id: int) -> None:
        async with self._lock:
            conn = self._require_conn()
            await conn.execute(
                "UPDATE dialogs SET unread_count = 0 WHERE id = ?",
                (dialog_id,),
            )
            await conn.commit()

    @_db_guard
    async def set_dialog_status(self, dialog_id: int, status: str) -> bool:
        if status not in {"open", "closed"}:
            raise ValueError("Недопустимый статус диалога.")
        async with self._lock:
            conn = self._require_conn()
            cursor = await conn.execute(
                """
                UPDATE dialogs
                SET status = ?,
                    updated_at = ?,
                    unread_count = CASE WHEN ? = 'closed' THEN 0 ELSE unread_count END
                WHERE id = ?
                """,
                (status, int(time.time()), status, dialog_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    @_db_guard
    async def set_blocked(
        self,
        telegram_id: int,
        blocked: bool,
        *,
        reason: str | None = None,
        now: int | None = None,
    ) -> bool:
        timestamp = int(time.time()) if now is None else now
        async with self._lock:
            conn = self._require_conn()
            if blocked:
                cursor = await conn.execute(
                    """
                    UPDATE users
                    SET is_blocked = 1, blocked_at = ?, blocked_reason = ?
                    WHERE telegram_id = ?
                    """,
                    (timestamp, (reason or "")[:256] or None, telegram_id),
                )
            else:
                cursor = await conn.execute(
                    """
                    UPDATE users
                    SET is_blocked = 0, blocked_at = NULL, blocked_reason = NULL
                    WHERE telegram_id = ?
                    """,
                    (telegram_id,),
                )
            await conn.commit()
            return cursor.rowcount > 0

    @_db_guard
    async def map_owner_message(
        self,
        owner_chat_id: int,
        owner_message_id: int,
        dialog_id: int,
        *,
        now: int | None = None,
    ) -> None:
        timestamp = int(time.time()) if now is None else now
        async with self._lock:
            conn = self._require_conn()
            await conn.execute(
                """
                INSERT INTO owner_messages (
                    owner_chat_id, owner_message_id, dialog_id, created_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(owner_chat_id, owner_message_id) DO UPDATE SET
                    dialog_id = excluded.dialog_id,
                    created_at = excluded.created_at
                """,
                (owner_chat_id, owner_message_id, dialog_id, timestamp),
            )
            await conn.commit()

    @_db_guard
    async def map_owner_messages(
        self,
        owner_chat_id: int,
        owner_message_ids: Sequence[int],
        dialog_id: int,
        *,
        now: int | None = None,
    ) -> None:
        if not owner_message_ids:
            return
        timestamp = int(time.time()) if now is None else now
        async with self._lock:
            conn = self._require_conn()
            await conn.executemany(
                """
                INSERT INTO owner_messages (
                    owner_chat_id, owner_message_id, dialog_id, created_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(owner_chat_id, owner_message_id) DO UPDATE SET
                    dialog_id = excluded.dialog_id,
                    created_at = excluded.created_at
                """,
                [
                    (owner_chat_id, int(mid), dialog_id, timestamp)
                    for mid in owner_message_ids
                ],
            )
            await conn.commit()

    @_db_guard
    async def unmap_owner_message(
        self,
        owner_chat_id: int,
        owner_message_id: int,
    ) -> None:
        async with self._lock:
            conn = self._require_conn()
            await conn.execute(
                """
                DELETE FROM owner_messages
                WHERE owner_chat_id = ? AND owner_message_id = ?
                """,
                (owner_chat_id, owner_message_id),
            )
            await conn.commit()

    @_db_guard
    async def resolve_dialog_by_owner_message(
        self,
        owner_chat_id: int,
        owner_message_id: int,
    ) -> DialogRecord | None:
        async with self._lock:
            conn = self._require_conn()
            cursor = await conn.execute(
                """
                SELECT dialog_id
                FROM owner_messages
                WHERE owner_chat_id = ? AND owner_message_id = ?
                """,
                (owner_chat_id, owner_message_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return await self._fetch_dialog_locked(int(row["dialog_id"]))

    @_db_guard
    async def get_latest_message(self, dialog_id: int) -> MessageRecord | None:
        async with self._lock:
            conn = self._require_conn()
            cursor = await conn.execute(
                """
                SELECT id, dialog_id, direction, kind, content, created_at
                FROM messages
                WHERE dialog_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (dialog_id,),
            )
            row = await cursor.fetchone()
            return self._row_to_message(row) if row is not None else None

    @_db_guard
    async def get_messages(
        self, dialog_id: int, limit: int = 15
    ) -> list[MessageRecord]:
        safe_limit = max(1, min(int(limit), 100))
        async with self._lock:
            conn = self._require_conn()
            cursor = await conn.execute(
                """
                SELECT id, dialog_id, direction, kind, content, created_at
                FROM messages
                WHERE dialog_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (dialog_id, safe_limit),
            )
            rows = await cursor.fetchall()
        return [self._row_to_message(row) for row in reversed(rows)]

    @_db_guard
    async def list_dialogs(
        self,
        *,
        limit: int = 8,
        offset: int = 0,
        unread_only: bool = False,
    ) -> tuple[list[DialogRecord], int]:
        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, int(offset))
        where = " WHERE d.unread_count > 0" if unread_only else ""
        async with self._lock:
            conn = self._require_conn()
            count_cursor = await conn.execute(
                "SELECT COUNT(*) AS total FROM dialogs AS d" + where
            )
            count_row = await count_cursor.fetchone()
            total = int(count_row["total"]) if count_row is not None else 0

            cursor = await conn.execute(
                DIALOG_SELECT
                + where
                + """
                ORDER BY d.updated_at DESC, d.id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            )
            rows = await cursor.fetchall()
        return [self._row_to_dialog(row) for row in rows], total

    @_db_guard
    async def list_users(
        self,
        *,
        limit: int = 8,
        offset: int = 0,
    ) -> tuple[list[DialogRecord], int]:
        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, int(offset))
        async with self._lock:
            conn = self._require_conn()
            count_cursor = await conn.execute("SELECT COUNT(*) AS total FROM users")
            count_row = await count_cursor.fetchone()
            total = int(count_row["total"]) if count_row is not None else 0

            cursor = await conn.execute(
                DIALOG_SELECT
                + """
                ORDER BY u.last_seen DESC, d.id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            )
            rows = await cursor.fetchall()
        return [self._row_to_dialog(row) for row in rows], total

    @_db_guard
    async def list_blocked(
        self,
        *,
        limit: int = 8,
        offset: int = 0,
    ) -> tuple[list[DialogRecord], int]:
        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, int(offset))
        async with self._lock:
            conn = self._require_conn()
            count_cursor = await conn.execute(
                "SELECT COUNT(*) AS total FROM users WHERE is_blocked = 1"
            )
            count_row = await count_cursor.fetchone()
            total = int(count_row["total"]) if count_row is not None else 0

            cursor = await conn.execute(
                DIALOG_SELECT
                + """
                WHERE u.is_blocked = 1
                ORDER BY u.blocked_at DESC, d.id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            )
            rows = await cursor.fetchall()
        return [self._row_to_dialog(row) for row in rows], total

    @_db_guard
    async def get_stats(self) -> StatsRecord:
        async with self._lock:
            conn = self._require_conn()
            cursor = await conn.execute(
                """
                SELECT
                    (SELECT COALESCE(SUM(unread_count), 0) FROM dialogs) AS new_messages,
                    (SELECT COUNT(*) FROM dialogs WHERE status = 'open') AS active_dialogs,
                    (SELECT COUNT(*) FROM users) AS total_users,
                    (SELECT COUNT(*) FROM users WHERE is_blocked = 1) AS blocked_users
                """
            )
            row = await cursor.fetchone()
            if row is None:
                return StatsRecord(0, 0, 0, 0)
            return StatsRecord(
                new_messages=int(row["new_messages"]),
                active_dialogs=int(row["active_dialogs"]),
                total_users=int(row["total_users"]),
                blocked_users=int(row["blocked_users"]),
            )

    @_db_guard
    async def cleanup_old_data(
        self,
        *,
        history_cutoff: int,
        updates_cutoff: int,
    ) -> dict[str, int]:
        async with self._lock:
            conn = self._require_conn()
            deleted_messages = await conn.execute(
                "DELETE FROM messages WHERE created_at < ?",
                (history_cutoff,),
            )
            deleted_mappings = await conn.execute(
                "DELETE FROM owner_messages WHERE created_at < ?",
                (history_cutoff,),
            )
            deleted_updates = await conn.execute(
                "DELETE FROM processed_updates WHERE processed_at < ?",
                (updates_cutoff,),
            )
            await conn.commit()
            return {
                "messages": max(0, deleted_messages.rowcount),
                "owner_mappings": max(0, deleted_mappings.rowcount),
                "processed_updates": max(0, deleted_updates.rowcount),
            }

    @_db_guard
    async def claim_update(self, update_id: int, *, now: int | None = None) -> bool:
        """Атомарно отмечает update обработанным.

        Возвращает True только для первого получения update_id.
        """

        timestamp = int(time.time()) if now is None else now
        async with self._lock:
            conn = self._require_conn()
            cursor = await conn.execute(
                """
                INSERT OR IGNORE INTO processed_updates (update_id, processed_at)
                VALUES (?, ?)
                """,
                (update_id, timestamp),
            )
            claimed = cursor.rowcount > 0

            self._updates_since_cleanup += 1
            if self._updates_since_cleanup >= 1000:
                self._updates_since_cleanup = 0
                await conn.execute(
                    "DELETE FROM processed_updates WHERE processed_at < ?",
                    (timestamp - 7 * 86_400,),
                )
            await conn.commit()
            return claimed
