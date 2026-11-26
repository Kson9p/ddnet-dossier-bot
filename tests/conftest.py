from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from config import Settings
from database import Database


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    settings = Settings(
        bot_token="123456789:AAExampleExampleExampleExampleExample",
        owner_id=777,
        database_path=tmp_path / "bot.db",
        log_level="DEBUG",
        timezone="UTC",
        rate_limit_window_seconds=60,
        rate_limit_max_messages=30,
        rate_limit_min_interval_seconds=1.0,
        rate_limit_max_tracked_users=100,
        rate_limit_warning_cooldown_seconds=30,
        media_group_delay_seconds=0.8,
        media_group_max_buffers=50,
        media_group_max_items=10,
        history_retention_days=30,
        history_page_size=15,
        admin_page_size=8,
        telegram_max_retries=0,
        floodwait_max_seconds=60,
        maintenance_interval_seconds=3600,
    )
    return replace(settings, **overrides)


@pytest.fixture
async def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "bot.db")
    await db.connect()
    await db.initialize()
    yield db
    await db.close()


def message(
    message_id: int,
    user_id: int,
    *,
    text: str | None = None,
    caption: str | None = None,
    media_group_id: str | None = None,
    full_name: str = "Пользователь",
    username: str | None = "user",
    photo: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        message_id=message_id,
        chat=SimpleNamespace(id=user_id, type="private"),
        from_user=SimpleNamespace(
            id=user_id,
            full_name=full_name,
            username=username,
        ),
        text=text,
        caption=caption,
        media_group_id=media_group_id,
        photo=object() if photo else None,
        video=None,
        video_note=None,
        voice=None,
        audio=None,
        animation=None,
        document=None,
        sticker=None,
        contact=None,
        location=None,
        venue=None,
        poll=None,
        dice=None,
    )
