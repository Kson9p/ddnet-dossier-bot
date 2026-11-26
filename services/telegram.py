"""Повторные вызовы Telegram API при FloodWait и сетевых сбоях."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.exceptions import (
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


async def safe_telegram_call(
    factory: Callable[[], Awaitable[T]],
    *,
    operation: str,
    retries: int = 2,
    max_retry_after: int = 60,
) -> T:
    """Выполняет запрос, уважая Telegram RetryAfter.

    Если Telegram требует паузу больше разрешённого максимума, вызов
    завершается ошибкой, чтобы не блокировать обработку на минуты.
    """

    attempt = 0
    while True:
        try:
            return await factory()
        except TelegramRetryAfter as exc:
            if attempt >= retries or exc.retry_after > max_retry_after:
                logger.warning(
                    "Telegram FloodWait при операции %s: %s сек., повторов больше нет",
                    operation,
                    exc.retry_after,
                )
                raise
            attempt += 1
            logger.warning(
                "Telegram FloodWait при операции %s: пауза %s сек.",
                operation,
                exc.retry_after,
            )
            await asyncio.sleep(float(exc.retry_after) + 0.05)
        except (TelegramNetworkError, TelegramServerError) as exc:
            if attempt >= retries:
                logger.warning(
                    "Telegram временно недоступен при операции %s: %s",
                    operation,
                    type(exc).__name__,
                )
                raise
            attempt += 1
            delay = min(0.5 * (2 ** (attempt - 1)), 4.0)
            logger.warning(
                "Сетевой сбой Telegram при операции %s (%s), повтор через %.1f сек.",
                operation,
                type(exc).__name__,
                delay,
            )
            await asyncio.sleep(delay)
