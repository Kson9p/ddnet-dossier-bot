from __future__ import annotations

from pathlib import Path

import pytest

from database import Database


@pytest.fixture
async def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.initialize()
    yield db
    await db.close()


async def test_user_dialog_and_stats(database: Database) -> None:
    dialog = await database.get_or_create_dialog(1001, "Иван", "ivan", now=100)
    assert dialog.id == 1
    assert dialog.display_name == "Иван"
    assert dialog.username == "ivan"
    assert dialog.unread_count == 0

    again = await database.get_or_create_dialog(1001, "Иван Петров", None, now=200)
    assert again.id == dialog.id
    assert again.display_name == "Иван Петров"
    assert again.username is None

    await database.record_incoming(again.id, "text", "привет", now=300)
    await database.record_incoming(again.id, "photo", "подпись", now=301)
    stats = await database.get_stats()
    assert stats.new_messages == 2
    assert stats.active_dialogs == 1
    assert stats.total_users == 1
    assert stats.blocked_users == 0

    messages = await database.get_messages(again.id, 10)
    assert [message.direction for message in messages] == ["in", "in"]
    assert messages[-1].content == "подпись"

    await database.mark_read(again.id)
    assert (await database.get_stats()).new_messages == 0


async def test_mapping_survives_reconnect(tmp_path: Path) -> None:
    path = tmp_path / "persist.db"
    db = Database(path)
    await db.connect()
    await db.initialize()
    dialog = await db.get_or_create_dialog(2002, "Пользователь", "user", now=100)
    await db.map_owner_message(777, 9001, dialog.id, now=101)
    resolved = await db.resolve_dialog_by_owner_message(777, 9001)
    assert resolved is not None
    assert resolved.id == dialog.id
    await db.close()

    db2 = Database(path)
    await db2.connect()
    await db2.initialize()
    resolved_after_restart = await db2.resolve_dialog_by_owner_message(777, 9001)
    assert resolved_after_restart is not None
    assert resolved_after_restart.user_id == 2002
    await db2.close()


async def test_block_and_lists(database: Database) -> None:
    first = await database.get_or_create_dialog(3003, "Анна", None, now=100)
    second = await database.get_or_create_dialog(4004, "Борис", "boris", now=101)
    await database.record_incoming(second.id, "text", "hello", now=102)

    assert await database.set_blocked(first.user_id, True, reason="spam", now=103)
    blocked, total = await database.list_blocked(limit=10, offset=0)
    assert total == 1
    assert blocked[0].id == first.id
    assert blocked[0].is_blocked

    users, total_users = await database.list_users(limit=10, offset=0)
    assert total_users == 2
    assert {item.id for item in users} == {first.id, second.id}
    assert (await database.get_stats()).blocked_users == 1

    assert await database.set_blocked(first.user_id, False)
    blocked_after, total_after = await database.list_blocked(limit=10, offset=0)
    assert total_after == 0
    assert blocked_after == []


async def test_dedupe_and_cleanup(database: Database) -> None:
    assert await database.claim_update(10, now=1_000) is True
    assert await database.claim_update(10, now=1_001) is False
    assert await database.claim_update(11, now=1_002) is True

    dialog = await database.get_or_create_dialog(5005, "Тест", None, now=100)
    await database.record_incoming(dialog.id, "text", "old", now=100)
    await database.map_owner_message(777, 12345, dialog.id, now=100)

    deleted = await database.cleanup_old_data(history_cutoff=500, updates_cutoff=2_000)
    assert deleted["messages"] == 1
    assert deleted["owner_mappings"] == 1
    assert deleted["processed_updates"] == 2
    assert await database.get_messages(dialog.id, 10) == []
    assert await database.resolve_dialog_by_owner_message(777, 12345) is None
