from __future__ import annotations

import asyncio

import ui
from callbacks import AdminUserCB, DialogCB, ListCB, MenuCB, UserCB
from database import DialogRecord, MessageRecord
from services.content import MessageContent
from services.media_groups import MediaGroupBuffer
from services.rate_limit import RateLimiter
from tests.conftest import message


async def test_rate_limiter_interval_quota_and_bounded_users() -> None:
    limiter = RateLimiter(
        window_seconds=60,
        max_messages=2,
        min_interval_seconds=5,
        max_tracked_users=2,
        warning_cooldown_seconds=30,
    )
    assert limiter.allow(1).allowed
    assert not limiter.allow(1).allowed
    assert limiter.allow(1, is_album=True).allowed
    assert not limiter.allow(1).allowed

    assert limiter.warning_due(1)
    assert not limiter.warning_due(1)

    assert limiter.allow(2).allowed
    assert limiter.allow(3).allowed
    assert limiter.allow(4).allowed
    assert len(limiter._history) <= 2


async def test_media_group_buffer_flushes_once() -> None:
    buffer = MediaGroupBuffer(delay_seconds=0.02, max_buffers=10, max_items=10)
    received: list[list[int]] = []
    event = asyncio.Event()

    async def callback(messages) -> None:
        received.append([item.message_id for item in messages])
        event.set()

    await buffer.add(message(1, 100, media_group_id="g1", photo=True), callback)
    await buffer.add(message(2, 100, media_group_id="g1", photo=True), callback)
    await asyncio.wait_for(event.wait(), timeout=1)

    assert received == [[1, 2]]
    assert buffer.pending_groups == 0
    await buffer.close()


async def test_media_group_buffer_max_items_flushes_immediately() -> None:
    buffer = MediaGroupBuffer(delay_seconds=10, max_buffers=10, max_items=2)
    received: list[list[int]] = []

    async def callback(messages) -> None:
        received.append([item.message_id for item in messages])

    await buffer.add(message(1, 100, media_group_id="g2", photo=True), callback)
    await buffer.add(message(2, 100, media_group_id="g2", photo=True), callback)
    await asyncio.sleep(0)
    assert received == [[1, 2]]
    await buffer.close(flush=False)


def test_card_html_is_limited_even_with_many_entities() -> None:
    from zoneinfo import ZoneInfo

    dialog = DialogRecord(
        id=1,
        user_id=123456789,
        display_name="&" * 128,
        username="a" * 64,
        first_seen=0,
        last_seen=0,
        messages_count=1,
        is_blocked=False,
        blocked_at=None,
        blocked_reason=None,
        status="open",
        unread_count=1,
        created_at=0,
        updated_at=0,
        last_message_at=0,
    )
    content = MessageContent(
        kind="text",
        label="Текст",
        text="&" * 10_000,
        attachment=False,
    )
    card = ui.new_message_card(dialog, content, 0, ZoneInfo("UTC"))
    assert len(card) <= 4096
    assert "&amp;" in card


def test_callback_data_is_short_and_structured() -> None:
    paylods = [
        MenuCB(action="home").pack(),
        MenuCB(action="blacklist").pack(),
        ListCB(section="dialogs", page=12).pack(),
        DialogCB(action="history", dialog_id=999999).pack(),
        AdminUserCB(action="unban", telegram_id=999999999999, page=10).pack(),
        UserCB(action="compose").pack(),
    ]
    assert all(len(payload.encode("utf-8")) <= 64 for payload in paylods)
    assert DialogCB.unpack("dlg:reply:12").action == "reply"


def test_owner_interface_hides_sender_personal_data() -> None:
    from zoneinfo import ZoneInfo

    import keyboards

    dialog = DialogRecord(
        id=12,
        user_id=123456789,
        display_name="Иван Секретный",
        username="private_handle",
        first_seen=100,
        last_seen=200,
        messages_count=1,
        is_blocked=False,
        blocked_at=None,
        blocked_reason=None,
        status="open",
        unread_count=1,
        created_at=100,
        updated_at=200,
        last_message_at=200,
    )
    latest = MessageRecord(
        id=1,
        dialog_id=12,
        direction="in",
        kind="text",
        content="Привет",
        created_at=200,
    )
    tz = ZoneInfo("UTC")
    new_message = ui.new_message_card(
        dialog, MessageContent("text", "Текст", "Привет", False), 200, tz
    )
    assert "🆔 ID: <code>123456789</code>" in new_message
    assert "👤 Отправитель: Иван Секретный · @private_handle" in new_message
    owner_texts = [
        ui.dialog_card_text(dialog, latest, tz),
        ui.profile_text(dialog, tz),
        ui.history_text(dialog, [latest], tz),
        ui.dialogs_list_text(
            [dialog], page=0, total=1, page_size=8, unread_only=True
        ),
        ui.users_list_text([dialog], page=0, total=1, page_size=8),
        ui.blacklist_text([dialog], page=0, total=1, page_size=8),
    ]
    for text in owner_texts:
        assert "Иван Секретный" not in text
        assert "private_handle" not in text
        assert "123456789" not in text

    keyboards_to_check = [
        keyboards.dialog_list_keyboard(
            [dialog], section="new", page=0, total=1, page_size=8
        ),
        keyboards.user_list_keyboard([dialog], page=0, total=1, page_size=8),
        keyboards.blacklist_keyboard([dialog], page=0, total=1, page_size=8),
    ]
    for markup in keyboards_to_check:
        labels = " ".join(
            button.text for row in markup.inline_keyboard for button in row
        )
        assert "Иван Секретный" not in labels
        assert "private_handle" not in labels
        assert "123456789" not in labels


def test_user_privacy_and_delivery_text() -> None:
    import keyboards

    assert "владелец видит твоё имя, username и " in ui.welcome_text()
    assert "владелец видит имя, username и Telegram ID" in ui.user_help_text()
    assert "Просто напиши сообщение ниже" not in ui.welcome_text()
    assert ui.delivery_success_user_text() == (
        "✅ Ваше сообщение доставлено владельцу.\n\n"
        "Хотите отправить ещё одно сообщение?"
    )
    button = keyboards.delivery_success_keyboard().inline_keyboard[0][0]
    assert button.text == "✍️ Написать ещё"
    assert UserCB.unpack(button.callback_data).action == "compose"


def test_owner_reply_success_offers_to_reply_again() -> None:
    import keyboards

    assert "Ответ отправлен в диалог #12" in ui.owner_reply_success_text(12)
    assert "Хотите написать ещё одно сообщение?" in ui.owner_reply_success_text(12)
    button = keyboards.owner_reply_again_keyboard(
        DialogRecord(
            id=12,
            user_id=123456789,
            display_name="Аноним",
            username=None,
            first_seen=100,
            last_seen=200,
            messages_count=1,
            is_blocked=False,
            blocked_at=None,
            blocked_reason=None,
            status="open",
            unread_count=0,
            created_at=100,
            updated_at=200,
            last_message_at=200,
        )
    ).inline_keyboard[0][0]
    assert button.text == "↩️ Ответить ещё"
    assert DialogCB.unpack(button.callback_data).action == "reply"
