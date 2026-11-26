"""Run both bots in one interpreter to avoid duplicating Python and aiogram."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram.utils.token import extract_bot_id

from dossier_bot.config import ConfigError, load_optional_settings
from dossier_bot.main import run

logger = logging.getLogger(__name__)


def _same_database(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    try:
        return first.samefile(second)
    except FileNotFoundError:
        return False


async def run_dossier_after_polling(
    ready: asyncio.Event, feedback_bot_id: int, feedback_db: Path
) -> None:
    try:
        settings = load_optional_settings()
        if settings is None:
            logger.info("[Досье] DOSSIER_BOT_TOKEN не задан; запущена только Подслушка.")
            return
        if extract_bot_id(settings.token) == feedback_bot_id:
            raise ConfigError("В DOSSIER_BOT_TOKEN нужен токен другого бота.")
        if _same_database(feedback_db, settings.database_path):
            raise ConfigError("Для DOSSIER_DATABASE_PATH нужен отдельный файл базы.")
    except ConfigError as exc:
        logger.error("[Досье] %s", exc)
        return
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("[Досье] Не удалось проверить настройки (%s).", type(exc).__name__)
        return

    logger.info("[Досье] Ждём первый успешный ответ polling Подслушки.")
    await ready.wait()
    logger.info("[Досье] Запускаем второго бота в общем процессе Python.")
    try:
        await run(settings, handle_signals=False, serve_web=True)
    except Exception as exc:
        logger.error("[Досье] Бот остановлен (%s). Подслушка работает дальше.", type(exc).__name__)
