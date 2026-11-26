from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import ui
from database import Database
from services.content import extract_single
from services.relay import RelayService
from tests.conftest import make_settings, message

OWNER_ID = 777


class FakeTelegram:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_message_id = 100

    def _new_message_id(self) -> int:
        self._next_message_id += 1
        return self._next_message_id

    async def send_message(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("send_message", kwargs))
        return SimpleNamespace(message_id=self._new_message_id())

    async def copy_message(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("copy_message", kwargs))
        return SimpleNamespace(message_id=self._new_message_id())

    async def copy_messages(self, **kwargs: Any) -> list[SimpleNamespace]:
        self.calls.append(("copy_messages", kwargs))
        return [
            SimpleNamespace(message_id=self._new_message_id())
            for _ in kwargs["message_ids"]
        ]

    async def edit_message_text(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("edit_message_text", kwargs))
        return SimpleNamespace(message_id=kwargs["message_id"])


@pytest.fixture
async def setup(tmp_path):
    db = Database(tmp_path / "relay.db")
    await db.connect()
    await db.initialize()
    settings = make_settings(tmp_path)
    bot = FakeTelegram()
    relay = RelayService(bot, db, settings)
    yield db, bot, relay
    await db.close()


async def test_user_text_card_and_owner_reply(setup) -> None:
    db, bot, relay = setup
    user_id = 1001
    dialog = await db.get_or_create_dialog(user_id, "Иван", "ivan")
    incoming = message(11, user_id, text="Привет, это тест")
    content = extract_single(incoming)
    assert content is not None

    delivered = await relay.deliver_user_message(incoming, dialog, content)
    assert delivered is True

    sends = [call for call in bot.calls if call[0] == "send_message"]
    assert len(sends) == 1
    card_kwargs = sends[0][1]
    assert card_kwargs["chat_id"] == OWNER_ID
    assert "НОВОЕ СООБЩЕНИЕ" in card_kwargs["text"]
    assert "Привет, это тест" in card_kwargs["text"]
    assert f"🆔 ID: <code>{user_id}</code>" in card_kwargs["text"]
    assert "👤 Отправитель: Иван · @ivan" in card_kwargs["text"]

    card_id = 101
    resolved = await db.resolve_dialog_by_owner_message(OWNER_ID, card_id)
    assert resolved is not None
    assert resolved.id == dialog.id

    owner_message = message(500, OWNER_ID, text="Ответ пользователю")
    assert await relay.deliver_owner_message(owner_message, resolved)

    copies = [call for call in bot.calls if call[0] == "copy_message"]
    assert len(copies) == 1
    assert copies[0][1]["chat_id"] == user_id
    assert copies[0][1]["from_chat_id"] == OWNER_ID
    assert copies[0][1]["message_id"] == 500

    history = await db.get_messages(dialog.id, 10)
    assert [item.direction for item in history] == ["in", "out"]


async def test_two_users_are_routed_independently(setup) -> None:
    db, bot, relay = setup
    first = await db.get_or_create_dialog(2001, "Первый", "first")
    second = await db.get_or_create_dialog(2002, "Второй", "second")

    first_content = extract_single(message(21, 2001, text="От первого"))
    second_content = extract_single(message(22, 2002, text="От второго"))
    assert first_content is not None and second_content is not None
    await relay.deliver_user_message(
        message(21, 2001, text="От первого"), first, first_content
    )
    await relay.deliver_user_message(
        message(22, 2002, text="От второго"), second, second_content
    )

    cards = [call[1] for call in bot.calls if call[0] == "send_message"]
    assert len(cards) == 2
    first_card_id = 101
    second_card_id = 102

    first_target = await db.resolve_dialog_by_owner_message(OWNER_ID, first_card_id)
    second_target = await db.resolve_dialog_by_owner_message(OWNER_ID, second_card_id)
    assert first_target is not None and second_target is not None

    await relay.deliver_owner_message(
        message(600, OWNER_ID, text="Ответ первому"),
        first_target,
    )
    await relay.deliver_owner_message(
        message(601, OWNER_ID, text="Ответ второму"),
        second_target,
    )

    copies = [call[1] for call in bot.calls if call[0] == "copy_message"]
    assert [(item["chat_id"], item["message_id"]) for item in copies] == [
        (2001, 600),
        (2002, 601),
    ]
    assert all(call[0] != "forward_message" for call in bot.calls)


async def test_album_sends_one_card_and_group(setup) -> None:
    db, bot, relay = setup
    first = message(
        31,
        3001,
        caption="Альбом",
        media_group_id="album-1",
        photo=True,
        full_name="Альбомный",
        username=None,
    )
    second = message(
        32,
        3001,
        media_group_id="album-1",
        photo=True,
        full_name="Альбомный",
        username=None,
    )

    assert await relay.deliver_user_album([first, second]) is True
    sends = [call for call in bot.calls if call[0] == "send_message"]
    copies = [call for call in bot.calls if call[0] == "copy_messages"]
    assert len(sends) == 1
    assert len(copies) == 1
    assert copies[0][1]["message_ids"] == [31, 32]
    assert "Альбом · 2" in sends[0][1]["text"]

    dialog = await db.get_dialog_by_user(3001)
    assert dialog is not None
    assert dialog.unread_count == 2
    history = await db.get_messages(dialog.id, 10)
    assert len(history) == 1
    assert history[0].kind == "album"

    for copied_id in (102, 103):
        assert await db.resolve_dialog_by_owner_message(OWNER_ID, copied_id) is not None


async def test_long_text_is_copied_after_card(setup) -> None:
    db, bot, relay = setup
    dialog = await db.get_or_create_dialog(4001, "Длинный", "long")
    text = "а" * (ui.CARD_TEXT_LIMIT + 100)
    incoming = message(41, 4001, text=text)
    content = extract_single(incoming)
    assert content is not None

    await relay.deliver_user_message(incoming, dialog, content)
    methods = [call[0] for call in bot.calls]
    assert methods == ["send_message", "copy_message"]
    copied = next(call for call in bot.calls if call[0] == "copy_message")[1]
    assert copied["chat_id"] == OWNER_ID
    assert copied["from_chat_id"] == 4001
    assert copied["message_id"] == 41


@pytest.mark.parametrize(
    ("attribute", "kind"),
    [
        ("photo", "photo"),
        ("video", "video"),
        ("video_note", "video_note"),
        ("voice", "voice"),
        ("audio", "audio"),
        ("animation", "animation"),
        ("document", "document"),
        ("sticker", "sticker"),
    ],
)
async def test_supported_attachments_are_relayed_both_ways(
    setup,
    attribute: str,
    kind: str,
) -> None:
    db, bot, relay = setup
    user_id = 6001
    dialog = await db.get_or_create_dialog(user_id, "Медиа", "media_user")

    incoming = message(61, user_id, caption="Входящее вложение")
    setattr(incoming, attribute, object())
    content = extract_single(incoming)
    assert content is not None
    assert content.kind == kind
    assert await relay.deliver_user_message(incoming, dialog, content)

    owner_copy = next(
        kwargs
        for method, kwargs in bot.calls
        if method == "copy_message" and kwargs["chat_id"] == OWNER_ID
    )
    assert owner_copy["from_chat_id"] == user_id
    assert owner_copy["message_id"] == incoming.message_id

    outgoing = message(700, OWNER_ID, caption="Ответное вложение")
    setattr(outgoing, attribute, object())
    assert await relay.deliver_owner_message(outgoing, dialog)

    user_copy = [
        kwargs
        for method, kwargs in bot.calls
        if method == "copy_message" and kwargs["chat_id"] == user_id
    ]
    assert user_copy[-1]["from_chat_id"] == OWNER_ID
    assert user_copy[-1]["message_id"] == outgoing.message_id

    history = await db.get_messages(dialog.id, 10)
    assert [(record.direction, record.kind) for record in history] == [
        ("in", kind),
        ("out", kind),
    ]


async def test_restart_keeps_reply_routing(tmp_path) -> None:
    path = tmp_path / "restart.db"
    settings = make_settings(tmp_path)
    db = Database(path)
    await db.connect()
    await db.initialize()
    dialog = await db.get_or_create_dialog(5001, "Рестарт", "restart")
    await db.map_owner_message(OWNER_ID, 9001, dialog.id)
    await db.close()

    db2 = Database(path)
    await db2.connect()
    await db2.initialize()
    bot = FakeTelegram()
    relay = RelayService(bot, db2, settings)
    target = await db2.resolve_dialog_by_owner_message(OWNER_ID, 9001)
    assert target is not None
    assert await relay.deliver_owner_message(
        message(700, OWNER_ID, text="После рестарта"),
        target,
    )
    assert bot.calls[0][1]["chat_id"] == 5001
    await db2.close()
