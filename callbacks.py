"""Структурированные callback_data для inline-кнопок."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="menu"):
    action: str


class ListCB(CallbackData, prefix="list"):
    section: str
    page: int = 0


class DialogCB(CallbackData, prefix="dlg"):
    action: str
    dialog_id: int


class AdminUserCB(CallbackData, prefix="ausr"):
    action: str
    telegram_id: int
    page: int = 0


class UserCB(CallbackData, prefix="usr"):
    action: str
