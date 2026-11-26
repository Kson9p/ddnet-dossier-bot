"""Inline-клавиатуры для пользователя и владельца."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from callbacks import AdminUserCB, DialogCB, ListCB, MenuCB, UserCB
from database import DialogRecord


def user_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Написать сообщение",
                    callback_data=UserCB(action="compose").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Как это работает",
                    callback_data=UserCB(action="help").pack(),
                )
            ],
        ]
    )


def delivery_success_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Написать ещё",
                    callback_data=UserCB(action="compose").pack(),
                )
            ]
        ]
    )


def owner_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Сообщения", callback_data=MenuCB(action="new").pack()
                ),
                InlineKeyboardButton(
                    text="💬 Диалоги", callback_data=MenuCB(action="dialogs").pack()
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👥 Пользователи", callback_data=MenuCB(action="users").pack()
                ),
                InlineKeyboardButton(
                    text="🚫 Чёрный список",
                    callback_data=MenuCB(action="blacklist").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Настройки", callback_data=MenuCB(action="settings").pack()
                )
            ],
        ]
    )


def dialog_card_keyboard(dialog: DialogRecord) -> InlineKeyboardMarkup:
    block_text = "✅ Разблокировать" if dialog.is_blocked else "🚫 Заблокировать"
    block_action = "unblock" if dialog.is_blocked else "block"
    close_text = (
        "📂 Открыть диалог" if dialog.status == "closed" else "🗑 Закрыть диалог"
    )
    close_action = "reopen" if dialog.status == "closed" else "close"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Ответить",
                    callback_data=DialogCB(action="reply", dialog_id=dialog.id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📂 О диалоге",
                    callback_data=DialogCB(
                        action="profile", dialog_id=dialog.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="📜 История диалога",
                    callback_data=DialogCB(
                        action="history", dialog_id=dialog.id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=block_text,
                    callback_data=DialogCB(
                        action=block_action, dialog_id=dialog.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=close_text,
                    callback_data=DialogCB(
                        action=close_action, dialog_id=dialog.id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=DialogCB(
                        action="refresh", dialog_id=dialog.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🏠 В меню", callback_data=MenuCB(action="home").pack()
                ),
            ],
        ]
    )


def profile_keyboard(dialog: DialogRecord) -> InlineKeyboardMarkup:
    block_text = "✅ Разблокировать" if dialog.is_blocked else "🚫 Заблокировать"
    block_action = "unblock" if dialog.is_blocked else "block"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 История диалога",
                    callback_data=DialogCB(
                        action="history", dialog_id=dialog.id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=block_text,
                    callback_data=DialogCB(
                        action=block_action, dialog_id=dialog.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🗂 К диалогу",
                    callback_data=DialogCB(
                        action="refresh", dialog_id=dialog.id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню", callback_data=MenuCB(action="home").pack()
                )
            ],
        ]
    )


def history_keyboard(dialog: DialogRecord) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📂 О диалоге",
                    callback_data=DialogCB(
                        action="profile", dialog_id=dialog.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🗂 К диалогу",
                    callback_data=DialogCB(
                        action="refresh", dialog_id=dialog.id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню", callback_data=MenuCB(action="home").pack()
                )
            ],
        ]
    )


def reply_prompt_keyboard(dialog: DialogRecord) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✖️ Отменить",
                    callback_data=DialogCB(action="cancel", dialog_id=dialog.id).pack(),
                ),
                InlineKeyboardButton(
                    text="🏠 В меню", callback_data=MenuCB(action="home").pack()
                ),
            ]
        ]
    )


def owner_reply_again_keyboard(dialog: DialogRecord) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Ответить ещё",
                    callback_data=DialogCB(
                        action="reply", dialog_id=dialog.id
                    ).pack(),
                )
            ]
        ]
    )


def _pagination_rows(
    section: str, page: int, total: int, page_size: int
) -> list[list[InlineKeyboardButton]]:
    pages = max(1, (total + page_size - 1) // page_size)
    row: list[InlineKeyboardButton] = []
    if page > 0:
        row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=ListCB(section=section, page=page - 1).pack(),
            )
        )
    if page + 1 < pages:
        row.append(
            InlineKeyboardButton(
                text="Далее ➡️",
                callback_data=ListCB(section=section, page=page + 1).pack(),
            )
        )
    return [row] if row else []


def dialog_list_keyboard(
    dialogs: list[DialogRecord],
    *,
    section: str,
    page: int,
    total: int,
    page_size: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for dialog in dialogs:
        unread = f" · {dialog.unread_count}" if dialog.unread_count else ""
        text = f"{'🚫' if dialog.is_blocked else '💬'} Анонимный диалог #{dialog.id}{unread}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=DialogCB(action="open", dialog_id=dialog.id).pack(),
                )
            ]
        )
    rows.extend(_pagination_rows(section, page, total, page_size))
    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 В меню", callback_data=MenuCB(action="home").pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_list_keyboard(
    dialogs: list[DialogRecord],
    *,
    page: int,
    total: int,
    page_size: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for dialog in dialogs:
        text = f"💬 Анонимный диалог #{dialog.id}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=DialogCB(action="open", dialog_id=dialog.id).pack(),
                )
            ]
        )
    rows.extend(_pagination_rows("users", page, total, page_size))
    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 В меню", callback_data=MenuCB(action="home").pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def blacklist_keyboard(
    dialogs: list[DialogRecord],
    *,
    page: int,
    total: int,
    page_size: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for dialog in dialogs:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Разблокировать диалог #{dialog.id}",
                    callback_data=AdminUserCB(
                        action="unban", telegram_id=dialog.user_id, page=page
                    ).pack(),
                )
            ]
        )
    rows.extend(_pagination_rows("blacklist", page, total, page_size))
    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 В меню", callback_data=MenuCB(action="home").pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить", callback_data=MenuCB(action="settings").pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню", callback_data=MenuCB(action="home").pack()
                )
            ],
        ]
    )
