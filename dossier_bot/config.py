from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aiogram.utils.token import TokenValidationError, extract_bot_id
from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent


class ConfigError(RuntimeError):
    """Configuration error safe to print in hosting logs."""


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    owner_id: int
    database_path: Path
    about_text: str


def load_settings() -> Settings:
    settings = load_optional_settings()
    if settings is None:
        raise ConfigError("Укажите DOSSIER_BOT_TOKEN в окружении или dossier_bot/.env.")
    return settings


def load_optional_settings() -> Settings | None:
    load_dotenv(PACKAGE_DIR / ".env", override=False)
    token = os.getenv("DOSSIER_BOT_TOKEN", "").strip()
    if not token:
        return None
    try:
        bot_id = extract_bot_id(token)
    except (TokenValidationError, ValueError):
        raise ConfigError("Проверьте формат DOSSIER_BOT_TOKEN.") from None

    raw_owner = os.getenv("DOSSIER_OWNER_ID", "").strip()
    try:
        owner_id = int(raw_owner)
    except ValueError:
        raise ConfigError("Укажите числовой ID владельца в DOSSIER_OWNER_ID.") from None
    if owner_id <= 0:
        raise ConfigError("DOSSIER_OWNER_ID должен быть положительным числом.")
    if owner_id == bot_id:
        raise ConfigError("В DOSSIER_OWNER_ID укажите ID своего аккаунта, а не бота.")

    raw_path = os.getenv("DOSSIER_DATABASE_PATH", "").strip() or "data/dossiers.db"
    if "\x00" in raw_path:
        raise ConfigError("Проверьте DOSSIER_DATABASE_PATH.")
    try:
        database_path = Path(raw_path).expanduser()
    except RuntimeError:
        raise ConfigError("Проверьте DOSSIER_DATABASE_PATH.") from None
    if not database_path.is_absolute():
        database_path = PACKAGE_DIR / database_path
    about = os.getenv(
        "DOSSIER_ABOUT_TEXT",
        "Бот для личных досье DDNet. Каждое досье проверяет модератор; без отдельного решения оно не публикуется.",
    ).strip()[:500]
    return Settings(token, owner_id, database_path, about)
