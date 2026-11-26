"""Конфигурация приложения.

Все секреты и идентификаторы читаются только из переменных окружения.
Файл .env используется исключительно для локальной разработки.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


class ConfigError(RuntimeError):
    """Понятная пользователю ошибка конфигурации."""


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    owner_id: int
    database_path: Path
    log_level: str
    timezone: str

    rate_limit_window_seconds: int
    rate_limit_max_messages: int
    rate_limit_min_interval_seconds: float
    rate_limit_max_tracked_users: int
    rate_limit_warning_cooldown_seconds: int

    media_group_delay_seconds: float
    media_group_max_buffers: int
    media_group_max_items: int

    history_retention_days: int
    history_page_size: int
    admin_page_size: int

    telegram_max_retries: int
    floodwait_max_seconds: int
    maintenance_interval_seconds: int

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def _get_int(
    env: dict[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
    errors: list[str],
) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{name} должен быть целым числом.")
        return default
    if not minimum <= value <= maximum:
        errors.append(f"{name} должен быть от {minimum} до {maximum}.")
        return default
    return value


def _get_float(
    env: dict[str, str],
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
    errors: list[str],
) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        errors.append(f"{name} должен быть числом.")
        return default
    if not minimum <= value <= maximum:
        errors.append(f"{name} должен быть от {minimum} до {maximum}.")
        return default
    return value


def load_settings(env_file: str | Path = ".env") -> Settings:
    """Загружает и валидирует настройки.

    Сообщения об ошибках не содержат значений секретов.
    """

    load_dotenv(dotenv_path=env_file, override=False)
    env = dict(os.environ)
    errors: list[str] = []

    bot_token = env.get("BOT_TOKEN", "").strip()
    if not bot_token:
        errors.append("BOT_TOKEN не задан. Укажите токен от @BotFather.")
    elif not TOKEN_RE.fullmatch(bot_token):
        errors.append("BOT_TOKEN имеет неверный формат. Проверьте токен от @BotFather.")

    owner_raw = env.get("OWNER_ID", "").strip()
    owner_id = 0
    if not owner_raw:
        errors.append("OWNER_ID не задан. Укажите Telegram ID владельца.")
    else:
        try:
            owner_id = int(owner_raw)
        except ValueError:
            errors.append("OWNER_ID должен быть числом (Telegram ID), а не username.")
        else:
            if owner_id <= 0:
                errors.append("OWNER_ID должен быть положительным Telegram ID.")

    db_raw = env.get("DATABASE_PATH", "data/bot.db").strip() or "data/bot.db"
    database_path = Path(db_raw).expanduser()
    if "\x00" in str(database_path):
        errors.append("DATABASE_PATH содержит недопустимый символ.")

    log_level = env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        errors.append(
            "LOG_LEVEL должен быть одним из: DEBUG, INFO, WARNING, ERROR, CRITICAL."
        )

    timezone = env.get("TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        errors.append(
            "TIMEZONE должен быть корректным именем часового пояса, например Europe/Moscow."
        )

    rate_limit_window_seconds = _get_int(
        env, "RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1, maximum=86_400, errors=errors
    )
    rate_limit_max_messages = _get_int(
        env, "RATE_LIMIT_MAX_MESSAGES", 30, minimum=1, maximum=10_000, errors=errors
    )
    rate_limit_min_interval_seconds = _get_float(
        env,
        "RATE_LIMIT_MIN_INTERVAL_SECONDS",
        1.0,
        minimum=0.0,
        maximum=3_600.0,
        errors=errors,
    )
    rate_limit_max_tracked_users = _get_int(
        env,
        "RATE_LIMIT_MAX_TRACKED_USERS",
        10_000,
        minimum=100,
        maximum=1_000_000,
        errors=errors,
    )
    rate_limit_warning_cooldown_seconds = _get_int(
        env,
        "RATE_LIMIT_WARNING_COOLDOWN_SECONDS",
        30,
        minimum=1,
        maximum=86_400,
        errors=errors,
    )

    media_group_delay_seconds = _get_float(
        env, "MEDIA_GROUP_DELAY_SECONDS", 0.8, minimum=0.2, maximum=5.0, errors=errors
    )
    media_group_max_buffers = _get_int(
        env, "MEDIA_GROUP_MAX_BUFFERS", 500, minimum=10, maximum=10_000, errors=errors
    )
    media_group_max_items = _get_int(
        env, "MEDIA_GROUP_MAX_ITEMS", 10, minimum=1, maximum=10, errors=errors
    )

    history_retention_days = _get_int(
        env, "HISTORY_RETENTION_DAYS", 30, minimum=1, maximum=3_650, errors=errors
    )
    history_page_size = _get_int(
        env, "HISTORY_PAGE_SIZE", 15, minimum=1, maximum=50, errors=errors
    )
    admin_page_size = _get_int(
        env, "ADMIN_PAGE_SIZE", 8, minimum=1, maximum=20, errors=errors
    )

    telegram_max_retries = _get_int(
        env, "TELEGRAM_MAX_RETRIES", 2, minimum=0, maximum=5, errors=errors
    )
    floodwait_max_seconds = _get_int(
        env, "FLOODWAIT_MAX_SECONDS", 60, minimum=1, maximum=600, errors=errors
    )
    maintenance_interval_seconds = _get_int(
        env,
        "MAINTENANCE_INTERVAL_SECONDS",
        21_600,
        minimum=300,
        maximum=604_800,
        errors=errors,
    )

    if errors:
        raise ConfigError("Проверьте настройки окружения:\n- " + "\n- ".join(errors))

    return Settings(
        bot_token=bot_token,
        owner_id=owner_id,
        database_path=database_path,
        log_level=log_level,
        timezone=timezone,
        rate_limit_window_seconds=rate_limit_window_seconds,
        rate_limit_max_messages=rate_limit_max_messages,
        rate_limit_min_interval_seconds=rate_limit_min_interval_seconds,
        rate_limit_max_tracked_users=rate_limit_max_tracked_users,
        rate_limit_warning_cooldown_seconds=rate_limit_warning_cooldown_seconds,
        media_group_delay_seconds=media_group_delay_seconds,
        media_group_max_buffers=media_group_max_buffers,
        media_group_max_items=media_group_max_items,
        history_retention_days=history_retention_days,
        history_page_size=history_page_size,
        admin_page_size=admin_page_size,
        telegram_max_retries=telegram_max_retries,
        floodwait_max_seconds=floodwait_max_seconds,
        maintenance_interval_seconds=maintenance_interval_seconds,
    )
