"""Middleware дедупликации Telegram update_id."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from database import Database, DatabaseError

logger = logging.getLogger(__name__)


class UpdateDeduperMiddleware(BaseMiddleware):
    """Не обрабатывает один и тот же update повторно после перезапуска/сбоя."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            try:
                claimed = await self._db.claim_update(event.update_id)
            except DatabaseError:
                # База временно недоступна: лучше обработать update, чем потерять его.
                logger.error(
                    "Не удалось проверить дубликат update, обработка продолжена"
                )
            else:
                if not claimed:
                    logger.warning("Повторный update_id пропущен")
                    return None
        return await handler(event, data)
