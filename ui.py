"""Формирование компактного русского интерфейса бота (HTML Telegram)."""

from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from config import Settings
from database import DialogRecord, MessageRecord, StatsRecord
from services.content import MessageContent

CARD_TEXT_LIMIT = 2800
HISTORY_ITEM_LIMIT = 180
HISTORY_TOTAL_LIMIT = 3600


def h(value: object) -> str:
    return html.escape(str(value), quote=False)


def sender_line(dialog: DialogRecord) -> str:
    name = h(dialog.display_name.strip() or "Без имени")
    if dialog.username:
        return f"{name} · @{h(dialog.username)}"
    return name


def escape_clipped(value: str, limit: int) -> str:
    """Экранирует HTML и гарантирует длину уже с учётом &amp; и других сущностей."""

    value = value.strip()
    escaped = html.escape(value, quote=False)
    if len(escaped) <= limit:
        return escaped

    low = 0
    high = len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if len(html.escape(value[:middle], quote=False)) <= max(0, limit - 1):
            low = middle
        else:
            high = middle - 1
    prefix = value[:low].rstrip()
    return html.escape(prefix, quote=False) + "…"


def format_dt(timestamp: int, tz: ZoneInfo, *, short: bool = False) -> str:
    dt = datetime.fromtimestamp(timestamp, tz)
    return dt.strftime("%H:%M" if short else "%d.%m.%Y %H:%M")


def status_text(dialog: DialogRecord) -> str:
    if dialog.is_blocked:
        return "🚫 Заблокирован"
    if dialog.status == "closed":
        return "⚪ Закрыт"
    return "🟢 Открыт"


def status_emoji(dialog: DialogRecord) -> str:
    return "🚫" if dialog.is_blocked else ("⚪" if dialog.status == "closed" else "🟢")


def kind_text(kind: str) -> str:
    return {
        "text": "Текст",
        "photo": "Фотография",
        "video": "Видео",
        "video_note": "Видеосообщение",
        "voice": "Голосовое",
        "audio": "Аудио",
        "animation": "GIF-анимация",
        "document": "Документ",
        "sticker": "Стикер",
        "album": "Альбом",
    }.get(kind, "Сообщение")


def welcome_text() -> str:
    return (
        "👋 <b>Привет!</b>\n\n"
        "Здесь ты можешь отправить сообщение владельцу бота.\n\n"
        "📩 Поддерживаются текст, фотографии, видео, голосовые сообщения, "
        "аудио, GIF, документы, стикеры и альбомы.\n\n"
        "💬 Владелец может ответить тебе прямо в этом чате. Ответ придёт "
        "от имени бота.\n\n"
        "🔐 В карточке нового сообщения владелец видит твоё имя, username и "
        "Telegram ID. Он также получает текст и вложения, чтобы ответить."
    )


def user_help_text() -> str:
    return (
        "ℹ️ <b>Как это работает</b>\n\n"
        "Отправь сюда текст, фото, видео, голосовое, аудио, GIF, документ, "
        "стикер или альбом.\n"
        "В карточке нового сообщения владелец видит имя, username и Telegram ID, "
        "а также содержимое сообщения. Ответ придёт от имени бота."
    )


def owner_help_text() -> str:
    return (
        "🛡 <b>Команды владельца</b>\n\n"
        "/menu — панель управления\n"
        "/cancel — отменить режим ответа\n"
        "/ban <code>#номер</code> — заблокировать диалог\n"
        "/unban <code>#номер</code> — разблокировать диалог\n\n"
        "💬 Нажми «Ответить» под карточкой, затем отправь один текст или "
        "вложение. Telegram Reply на карточку тоже работает во включённом режиме.\n\n"
        "📂 Карточка диалога, история и блокировка доступны кнопками."
    )


def owner_panel_text(stats: StatsRecord) -> str:
    return (
        "🛡 <b>ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n\n"
        f"📩 Новых сообщений: <b>{stats.new_messages}</b>\n"
        f"💬 Активных диалогов: <b>{stats.active_dialogs}</b>\n"
        f"👥 Всего пользователей: <b>{stats.total_users}</b>\n"
        f"🚫 Заблокировано: <b>{stats.blocked_users}</b>"
    )


def new_message_card(
    dialog: DialogRecord,
    content: MessageContent,
    received_at: int,
    tz: ZoneInfo,
) -> str:
    if content.text.strip():
        text = escape_clipped(content.text, CARD_TEXT_LIMIT)
    else:
        text = "Без подписи." if content.attachment else "—"

    lines = [
        "🔎 <b>НОВОЕ СООБЩЕНИЕ</b>",
        "",
        f"🆔 ID: <code>{dialog.user_id}</code>",
        f"👤 Отправитель: {sender_line(dialog)}",
        f"💬 Диалог: <code>#{dialog.id}</code>",
        f"🕒 Получено: {format_dt(received_at, tz, short=True)}",
    ]
    if content.attachment:
        lines.append(f"📎 Вложение: {h(content.label)}")
    lines.extend(["", "📩 <b>Сообщение:</b>", text])
    if content.attachment and content.items_count > 1:
        lines.extend(
            [
                "",
                "ℹ️ Все файлы альбома передаются отдельным сообщением без потери качества.",
            ]
        )
    return "\n".join(lines)


def dialog_card_text(
    dialog: DialogRecord,
    latest: MessageRecord | None,
    tz: ZoneInfo,
) -> str:
    if latest is None:
        message_block = "—"
        message_title = "📩 Последнее сообщение:"
    else:
        message_title = (
            "📤 Последнее отправлено:"
            if latest.direction == "out"
            else "📩 Последнее сообщение:"
        )
        body = (
            escape_clipped(latest.content, CARD_TEXT_LIMIT) if latest.content else "—"
        )
        message_block = f"<i>{h(kind_text(latest.kind))}</i>\n{body}"

    return (
        f"🗂 <b>ДИАЛОГ #{dialog.id}</b>\n\n"
        f"📌 Статус: {status_text(dialog)}\n"
        f"📬 Непрочитанных: <b>{dialog.unread_count}</b>\n"
        f"🕒 Обновлён: {format_dt(dialog.updated_at, tz, short=True)}\n\n"
        f"{message_title}\n{message_block}"
    )


def profile_text(dialog: DialogRecord, tz: ZoneInfo) -> str:
    status = status_text(dialog)
    if dialog.is_blocked and dialog.blocked_at:
        status += f" · {format_dt(dialog.blocked_at, tz, short=True)}"
    return (
        f"📂 <b>ДИАЛОГ #{dialog.id}</b>\n\n"
        f"📅 Первое обращение: {format_dt(dialog.first_seen, tz)}\n"
        f"🕒 Последняя активность: {format_dt(dialog.last_seen, tz)}\n"
        f"✉️ Сообщений от пользователя: <b>{dialog.messages_count}</b>\n"
        f"📌 Статус: {status}"
    )


def history_text(
    dialog: DialogRecord,
    messages: list[MessageRecord],
    tz: ZoneInfo,
) -> str:
    header = (
        f"📜 <b>ИСТОРИЯ ДИАЛОГА #{dialog.id}</b>\n"
    )
    if not messages:
        return header + "\n<i>История пока пуста.</i>"

    blocks: list[str] = []
    used = len(header)
    for message in messages:
        direction = "👤 Пользователь" if message.direction == "in" else "🤖 Бот"
        raw_body = (message.content or "").strip() or kind_text(message.kind)
        body = escape_clipped(raw_body, HISTORY_ITEM_LIMIT)
        block = (
            f"\n🕒 {format_dt(message.created_at, tz, short=True)} · {direction}\n"
            f"<i>{h(kind_text(message.kind))}</i>\n{body}"
        )
        if used + len(block) > HISTORY_TOTAL_LIMIT:
            blocks.append("\n<i>…более старые сообщения скрыты.</i>")
            break
        blocks.append(block)
        used += len(block)

    return (
        header
        + "".join(blocks)
        + "\n\n<i>Хранятся только текстовые превью без медиафайлов.</i>"
    )


def _page_count(total: int, page_size: int) -> int:
    return max(1, (total + page_size - 1) // page_size)


def dialogs_list_text(
    dialogs: list[DialogRecord],
    *,
    page: int,
    total: int,
    page_size: int,
    unread_only: bool,
) -> str:
    title = "📩 <b>НОВЫЕ СООБЩЕНИЯ</b>" if unread_only else "💬 <b>ДИАЛОГИ</b>"
    pages = _page_count(total, page_size)
    if not dialogs:
        empty = "Новых сообщений нет." if unread_only else "Диалогов пока нет."
        return f"{title}\n\n<i>{empty}</i>"

    lines = [title, f"Страница {page + 1} из {pages} · всего: {total}", ""]
    for dialog in dialogs:
        unread = f" · 📬 {dialog.unread_count}" if dialog.unread_count else ""
        lines.append(
            f"{status_emoji(dialog)} <code>#{dialog.id}</code> · "
            f"анонимный диалог{unread}"
        )
    return "\n".join(lines)


def users_list_text(
    dialogs: list[DialogRecord],
    *,
    page: int,
    total: int,
    page_size: int,
) -> str:
    pages = _page_count(total, page_size)
    if not dialogs:
        return "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n<i>Пользователей пока нет.</i>"
    lines = [
        "👥 <b>ПОЛЬЗОВАТЕЛИ</b>",
        f"Страница {page + 1} из {pages} · всего: {total}",
        "",
    ]
    for dialog in dialogs:
        blocked = " 🚫" if dialog.is_blocked else ""
        lines.append(
            f"💬 Анонимный диалог <code>#{dialog.id}</code>{blocked}"
        )
    return "\n".join(lines)


def blacklist_text(
    dialogs: list[DialogRecord],
    *,
    page: int,
    total: int,
    page_size: int,
) -> str:
    pages = _page_count(total, page_size)
    if not dialogs:
        return "🚫 <b>ЧЁРНЫЙ СПИСОК</b>\n\n<i>Заблокированных пользователей нет.</i>"
    lines = [
        "🚫 <b>ЧЁРНЫЙ СПИСОК</b>",
        f"Страница {page + 1} из {pages} · всего: {total}",
        "",
    ]
    for dialog in dialogs:
        lines.append(
            f"🚫 Анонимный диалог <code>#{dialog.id}</code>"
        )
    return "\n".join(lines)


def settings_text(settings: Settings) -> str:
    return (
        "⚙️ <b>НАСТРОЙКИ</b>\n\n"
        f"🕒 Часовой пояс: <code>{h(settings.timezone)}</code>\n"
        f"⏱ Антиспам: <b>{settings.rate_limit_max_messages}</b> сообщений "
        f"за <b>{settings.rate_limit_window_seconds}</b> сек.\n"
        f"⏳ Минимальный интервал: <b>{settings.rate_limit_min_interval_seconds:g}</b> сек.\n"
        f"🖼 Сборка альбома: <b>{settings.media_group_delay_seconds:g}</b> сек.\n"
        f"🗂 Хранение истории: <b>{settings.history_retention_days}</b> дн.\n"
        f"📄 Элементов на странице: <b>{settings.admin_page_size}</b>\n\n"
        "<i>Значения задаются переменными окружения и не раскрывают секреты.</i>"
    )


def reply_prompt_text(dialog: DialogRecord) -> str:
    return (
        f"↩️ <b>Ответ для диалога #{dialog.id}</b>\n\n"
        "Отправьте текст или вложение. Оно уйдёт пользователю от имени бота."
    )


def owner_reply_success_text(dialog_id: int) -> str:
    return (
        f"✅ Ответ отправлен в диалог #{dialog_id}.\n\n"
        "Хотите написать ещё одно сообщение?"
    )


def owner_new_message_hint() -> str:
    return (
        "💬 Чтобы отправить ответ, нажмите «Ответить» под карточкой диалога. "
        "После отправки используйте кнопку «Ответить ещё» для следующего ответа.\n\n"
        "Открыть панель: /menu"
    )


def unsupported_user_text() -> str:
    return (
        "⚠️ Этот тип сообщения не поддерживается.\n\n"
        "Можно отправить текст, фото, видео, видеосообщение, голосовое, аудио, "
        "GIF, документ, стикер или альбом."
    )


def sensitive_owner_text() -> str:
    return (
        "⚠️ Контакт, геолокация и опросы не отправляются пользователю "
        "из соображений приватности. Отправьте текст или обычное вложение."
    )


def unsupported_owner_text() -> str:
    return (
        "⚠️ Этот тип сообщения нельзя отправить пользователю. "
        "Поддерживаются текст, фото, видео, голосовые, аудио, GIF, "
        "документы, стикеры и альбомы."
    )


def blocked_user_text() -> str:
    return "🚫 Отправка сообщений через этого бота сейчас недоступна."


def rate_limited_text(seconds: int) -> str:
    seconds = max(1, seconds)
    return f"⏳ Слишком часто. Попробуйте снова через {seconds} сек."


def delivery_failed_user_text() -> str:
    return "⚠️ Не удалось доставить сообщение. Попробуйте немного позже."


def delivery_success_user_text() -> str:
    return (
        "✅ Ваше сообщение доставлено владельцу.\n\n"
        "Хотите отправить ещё одно сообщение?"
    )


def compose_required_text() -> str:
    return "Сначала нажми «Написать сообщение», чтобы отправить текст или вложение."


def delivery_failed_owner_text(dialog_id: int) -> str:
    return f"⚠️ Не удалось передать вложение из диалога #{dialog_id}."


def user_blocked_bot_owner_text(dialog_id: int) -> str:
    return (
        f"⚠️ Ответ для диалога #{dialog_id} не доставлен: "
        "пользователь недоступен или заблокировал бота."
    )


def banned_notice() -> str:
    return "🚫 Отправка сообщений через этого бота ограничена."


def unbanned_notice() -> str:
    return "✅ Отправка сообщений снова доступна. Можете написать владельцу."


def dialog_not_found() -> str:
    return "⚠️ Диалог не найден или больше не существует."
