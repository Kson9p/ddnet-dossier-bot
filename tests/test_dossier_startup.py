from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram import Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import DeleteWebhook, GetMe, GetUpdates, SendMessage, SetMyCommands
from aiogram.types import User

import main as feedback
from dossier_bot.config import ConfigError, Settings, load_settings
from dossier_bot.main import run
from services import dossier_process
from tests.conftest import make_settings
from tests.test_handlers_integration import make_text_update

DOSSIER_TEST_TOKEN = "123456780:ExampleTokenForOfflineTestsOnly"
OWNER_ID = 777
DOSSIER_TEST_SECRET = "x" * 32
SOURCE_BOT_USERNAME = "ddnet_podslushka_bot"
CHANNEL_USERNAME = "ddnet_podslushka"


def dossier_settings(token, database_path):
    return Settings(
        token, OWNER_ID, database_path, "About", DOSSIER_TEST_SECRET,
        SOURCE_BOT_USERNAME, CHANNEL_USERNAME,
    )


def test_dossier_settings_use_host_environment(monkeypatch):
    monkeypatch.setattr("dossier_bot.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("DOSSIER_BOT_TOKEN", DOSSIER_TEST_TOKEN)
    monkeypatch.setenv("DOSSIER_OWNER_ID", str(OWNER_ID))
    monkeypatch.setenv("DOSSIER_DATABASE_PATH", "")
    monkeypatch.setenv("DOSSIER_LINK_SECRET", DOSSIER_TEST_SECRET)
    monkeypatch.setenv("DOSSIER_SOURCE_BOT_USERNAME", SOURCE_BOT_USERNAME)
    monkeypatch.setenv("DOSSIER_CHANNEL_USERNAME", CHANNEL_USERNAME)
    settings = load_settings()
    assert settings.owner_id == OWNER_ID
    assert settings.database_path.name == "dossiers.db"

    monkeypatch.setenv("DOSSIER_OWNER_ID", "@owner")
    with pytest.raises(ConfigError, match="DOSSIER_OWNER_ID"):
        load_settings()


async def test_feedback_polling_gates_second_process(monkeypatch, tmp_path):
    calls = 0
    ready_seen = asyncio.Event()
    settings = make_settings(tmp_path)

    async def request(self, bot, method, timeout=None):
        nonlocal calls
        if isinstance(method, GetMe):
            return User(id=bot.id, is_bot=True, first_name="Feedback", username="feedback_test_bot")
        if isinstance(method, (DeleteWebhook, SetMyCommands)):
            return True
        if isinstance(method, GetUpdates):
            calls += 1
            if calls == 1:
                raise TelegramNetworkError(method=method, message="offline test")
            return []
        pytest.fail(f"Unexpected API method: {type(method).__name__}")

    async def launch(ready, bot_id, database_path):
        assert database_path == settings.database_path
        await ready.wait()
        ready_seen.set()

    async def poll(self, bot, **kwargs):
        with pytest.raises(TelegramNetworkError):
            await bot(GetUpdates(timeout=1))
        await asyncio.sleep(0)
        assert not ready_seen.is_set()
        await bot(GetUpdates(timeout=1))
        await asyncio.wait_for(ready_seen.wait(), timeout=1)

    monkeypatch.setattr(AiohttpSession, "make_request", request)
    monkeypatch.setattr(feedback, "run_dossier_after_polling", launch)
    monkeypatch.setattr(Dispatcher, "start_polling", poll)
    assert await feedback.run_bot(settings) == 0


async def test_dossier_process_waits_for_readiness_and_stops(monkeypatch, tmp_path):
    settings = dossier_settings(DOSSIER_TEST_TOKEN, tmp_path / "dossiers.db")
    monkeypatch.setattr(dossier_process, "load_optional_settings", lambda: settings)

    launched = asyncio.Event()
    stopped = asyncio.Event()
    ready = asyncio.Event()

    async def run_bot(settings, *, handle_signals, serve_web):
        assert handle_signals is False
        assert serve_web is True
        launched.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(dossier_process, "run", run_bot)
    task = asyncio.create_task(dossier_process.run_dossier_after_polling(
        ready, 123456789, tmp_path / "bot.db"
    ))
    await asyncio.sleep(0)
    assert not launched.is_set()
    ready.set()
    await asyncio.wait_for(launched.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()


@pytest.mark.parametrize("problem", ["bot_id", "database"])
async def test_dossier_process_refuses_shared_settings(monkeypatch, tmp_path, caplog, problem):
    feedback_db = tmp_path / "bot.db"
    token = "123456789:ASecondTokenForTheSameBot" if problem == "bot_id" else DOSSIER_TEST_TOKEN
    dossier_db = feedback_db if problem == "database" else tmp_path / "dossiers.db"
    settings = dossier_settings(token, dossier_db)
    monkeypatch.setattr(dossier_process, "load_optional_settings", lambda: settings)
    spawn = AsyncMock()
    monkeypatch.setattr(dossier_process, "run", spawn)
    ready = asyncio.Event()
    ready.set()

    await dossier_process.run_dossier_after_polling(ready, 123456789, feedback_db)

    spawn.assert_not_called()
    assert "[Досье]" in caplog.text
    assert token not in caplog.text


async def test_dossier_start_replies_to_regular_account(monkeypatch, tmp_path):
    settings = dossier_settings(DOSSIER_TEST_TOKEN, tmp_path / "dossiers.db")
    messages = []
    methods = []
    ordinary_user = 778

    async def request(self, bot, method, timeout=None):
        methods.append(type(method))
        if isinstance(method, GetMe):
            return User(id=bot.id, is_bot=True, first_name="Dossier", username="dossier_test_bot")
        if isinstance(method, DeleteWebhook):
            assert method.drop_pending_updates is False
            return True
        if isinstance(method, GetUpdates):
            assert method.offset is None
            return []
        if isinstance(method, SendMessage):
            messages.append(method)
            return True
        pytest.fail(f"Unexpected API method: {type(method).__name__}")

    async def poll(self, bot, **kwargs):
        assert "message" in kwargs["allowed_updates"]
        for uid in (ordinary_user, OWNER_ID):
            await self.feed_update(bot, make_text_update(uid, user_id=uid, text="/start", message_id=1))

    monkeypatch.setattr(AiohttpSession, "make_request", request)
    monkeypatch.setattr(Dispatcher, "start_polling", poll)
    await run(settings)

    assert methods == [GetMe, DeleteWebhook, GetUpdates, SendMessage, SendMessage]
    menu, owner_reply = messages
    assert menu.chat_id == ordinary_user
    assert [button.callback_data for row in menu.reply_markup.inline_keyboard for button in row] == [
        "d:start", "s:start", "about",
    ]
    assert owner_reply.chat_id == OWNER_ID
    assert "Панель владельца" in owner_reply.text
