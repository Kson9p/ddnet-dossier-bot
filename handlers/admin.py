"""Обработчики владельца: панель, карточки, ответы, блокировки."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

import keyboards
import ui
from callbacks import AdminUserCB, DialogCB, ListCB, MenuCB
from config import Settings
from database import Database, DatabaseError, DialogRecord
from services.media_groups import MediaGroupBuffer
from services.relay import RelayService
from services.telegram import safe_telegram_call
from states import OwnerReplyStates

logger = logging.getLogger(__name__)


def create_admin_router(
    *,
    bot: Bot,
    settings: Settings,
    database: Database,
    relay: RelayService,
    media_buffer: MediaGroupBuffer,
) -> Router:
    router = Router(name="admin")
    router.message.filter(
        F.chat.type == "private",
        F.from_user.id == settings.owner_id,
    )
    router.callback_query.filter(
        F.message.chat.type == "private",
        F.from_user.id == settings.owner_id,
    )

    def is_owner_message(message: Message) -> bool:
        return (
            message.from_user is not None
            and message.from_user.id == settings.owner_id
            and message.chat.type == "private"
        )

    def is_owner_callback(callback: CallbackQuery) -> bool:
        return (
            callback.from_user.id == settings.owner_id
            and callback.message is not None
            and callback.message.chat.type == "private"
        )

    async def answer(
        callback: CallbackQuery,
        text: str | None = None,
        *,
        alert: bool = False,
    ) -> None:
        try:
            await callback.answer(text, show_alert=alert)
        except TelegramAPIError:
            logger.debug("Callback уже неактуален")

    async def send_owner(
        message: Message,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message | None:
        try:
            return await safe_telegram_call(
                lambda: message.answer(text, reply_markup=reply_markup),
                operation="owner_message_answer",
                retries=settings.telegram_max_retries,
                max_retry_after=settings.floodwait_max_seconds,
            )
        except TelegramAPIError as exc:
            logger.warning("Сообщение владельцу не доставлено: %s", type(exc).__name__)
            return None

    async def render(
        callback: CallbackQuery,
        text: str,
        reply_markup: InlineKeyboardMarkup,
        *,
        dialog_id: int | None = None,
        unmap: bool = False,
    ) -> bool:
        message = callback.message
        if message is None:
            return False

        target_id = message.message_id
        edited = False
        try:
            await safe_telegram_call(
                lambda: bot.edit_message_text(
                    chat_id=settings.owner_id,
                    message_id=message.message_id,
                    text=text,
                    reply_markup=reply_markup,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
                operation="admin_edit_message",
                retries=settings.telegram_max_retries,
                max_retry_after=settings.floodwait_max_seconds,
            )
            edited = True
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                edited = True
            else:
                logger.warning("Сообщение нельзя изменить: %s", type(exc).__name__)
        except TelegramAPIError as exc:
            logger.warning("Не удалось изменить сообщение: %s", type(exc).__name__)

        if not edited:
            try:
                sent = await safe_telegram_call(
                    lambda: bot.send_message(
                        chat_id=settings.owner_id,
                        text=text,
                        reply_markup=reply_markup,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    ),
                    operation="admin_send_message",
                    retries=settings.telegram_max_retries,
                    max_retry_after=settings.floodwait_max_seconds,
                )
            except TelegramAPIError as exc:
                logger.error("Панель не доставлена: %s", type(exc).__name__)
                return False
            target_id = sent.message_id

        try:
            if dialog_id is not None:
                await database.map_owner_message(
                    settings.owner_id, target_id, dialog_id
                )
            elif unmap:
                await database.unmap_owner_message(settings.owner_id, target_id)
        except DatabaseError:
            logger.error("Не удалось обновить привязку кнопок")
        return True

    async def show_panel(callback: CallbackQuery) -> None:
        stats = await database.get_stats()
        await render(
            callback,
            ui.owner_panel_text(stats),
            keyboards.owner_menu_keyboard(),
            unmap=True,
        )

    async def send_panel(message: Message) -> None:
        stats = await database.get_stats()
        await send_owner(
            message,
            ui.owner_panel_text(stats),
            reply_markup=keyboards.owner_menu_keyboard(),
        )

    async def show_list(callback: CallbackQuery, section: str, page: int) -> None:
        page_size = settings.admin_page_size
        page = max(0, page)

        if section == "new":
            dialogs, total = await database.list_dialogs(
                limit=page_size,
                offset=page * page_size,
                unread_only=True,
            )
            text_builder = lambda: ui.dialogs_list_text(
                dialogs,
                page=page,
                total=total,
                page_size=page_size,
                unread_only=True,
            )
            keyboard = keyboards.dialog_list_keyboard(
                dialogs,
                section="new",
                page=page,
                total=total,
                page_size=page_size,
            )
        elif section == "dialogs":
            dialogs, total = await database.list_dialogs(
                limit=page_size,
                offset=page * page_size,
            )
            text_builder = lambda: ui.dialogs_list_text(
                dialogs,
                page=page,
                total=total,
                page_size=page_size,
                unread_only=False,
            )
            keyboard = keyboards.dialog_list_keyboard(
                dialogs,
                section="dialogs",
                page=page,
                total=total,
                page_size=page_size,
            )
        elif section == "users":
            dialogs, total = await database.list_users(
                limit=page_size,
                offset=page * page_size,
            )
            text_builder = lambda: ui.users_list_text(
                dialogs,
                page=page,
                total=total,
                page_size=page_size,
            )
            keyboard = keyboards.user_list_keyboard(
                dialogs,
                page=page,
                total=total,
                page_size=page_size,
            )
        elif section == "blacklist":
            dialogs, total = await database.list_blocked(
                limit=page_size,
                offset=page * page_size,
            )
            text_builder = lambda: ui.blacklist_text(
                dialogs,
                page=page,
                total=total,
                page_size=page_size,
            )
            keyboard = keyboards.blacklist_keyboard(
                dialogs,
                page=page,
                total=total,
                page_size=page_size,
            )
        else:
            await show_panel(callback)
            return

        await render(callback, text_builder(), keyboard, unmap=True)

    async def get_dialog_or_none(
        callback: CallbackQuery, dialog_id: int
    ) -> DialogRecord | None:
        dialog = await database.get_dialog(dialog_id)
        if dialog is None:
            await answer(callback, ui.dialog_not_found(), alert=True)
        return dialog

    async def state_dialog_id(state: FSMContext) -> int | None:
        data = await state.get_data()
        value = data.get("dialog_id")
        return int(value) if isinstance(value, int) else None

    async def resolve_target(
        message: Message,
        state: FSMContext,
    ) -> DialogRecord | None:
        dialog_id = await state_dialog_id(state)
        if dialog_id is None:
            return None

        if message.reply_to_message is not None:
            dialog = await database.resolve_dialog_by_owner_message(
                settings.owner_id,
                message.reply_to_message.message_id,
            )
            if dialog is not None:
                return dialog

        return await database.get_dialog(dialog_id)

    async def route_owner_message(
        message: Message,
        state: FSMContext,
    ) -> None:
        dialog = await resolve_target(message, state)
        if dialog is None:
            await send_owner(
                message,
                ui.owner_new_message_hint(),
                reply_markup=keyboards.owner_menu_keyboard(),
            )
            return

        delivered = await relay.deliver_owner_message(message, dialog)
        if delivered:
            await state.clear()
            await send_owner(
                message,
                ui.owner_reply_success_text(dialog.id),
                reply_markup=keyboards.owner_reply_again_keyboard(dialog),
            )

    async def flush_owner_album(
        messages: Sequence[Message],
        state: FSMContext,
    ) -> None:
        if not messages:
            return
        dialog = await resolve_target(messages[0], state)
        if dialog is None:
            await send_owner(
                messages[0],
                ui.owner_new_message_hint(),
                reply_markup=keyboards.owner_menu_keyboard(),
            )
            return

        delivered = await relay.deliver_owner_album(messages, dialog)
        if delivered:
            await state.clear()
            await send_owner(
                messages[0],
                ui.owner_reply_success_text(dialog.id),
                reply_markup=keyboards.owner_reply_again_keyboard(dialog),
            )

    @router.message(Command("start", "menu", "panel", ignore_case=True))
    async def cmd_menu(message: Message, state: FSMContext) -> None:
        if not is_owner_message(message):
            return
        await state.clear()
        await send_panel(message)

    @router.message(Command("help", ignore_case=True))
    async def cmd_help(message: Message) -> None:
        if not is_owner_message(message):
            return
        await send_owner(
            message,
            ui.owner_help_text(),
            reply_markup=keyboards.owner_menu_keyboard(),
        )

    @router.message(Command("cancel", ignore_case=True))
    async def cmd_cancel(message: Message, state: FSMContext) -> None:
        if not is_owner_message(message):
            return
        await state.clear()
        await send_owner(
            message,
            "✖️ Режим ответа отменён.",
            reply_markup=keyboards.owner_menu_keyboard(),
        )

    @router.message(Command("ban", ignore_case=True))
    async def cmd_ban(
        message: Message,
        command: CommandObject,
        state: FSMContext,
    ) -> None:
        if not is_owner_message(message):
            return
        args = (command.args or "").strip()
        dialog: DialogRecord | None = None
        reason: str | None = None

        if message.reply_to_message is not None:
            dialog = await database.resolve_dialog_by_owner_message(
                settings.owner_id,
                message.reply_to_message.message_id,
            )
            reason = args or None
            if dialog is None:
                await send_owner(
                    message,
                    "⚠️ Это сообщение не привязано к диалогу. Ответьте на карточку "
                    "полученного сообщения или укажите <code>#номер диалога</code>.",
                )
                return
        elif args:
            parts = args.split(maxsplit=1)
            raw_target = parts[0]
            reason = parts[1] if len(parts) > 1 else None
            if raw_target.startswith("#") and raw_target[1:].isdigit():
                dialog = await database.get_dialog(int(raw_target[1:]))
            else:
                await send_owner(
                    message,
                    "⚠️ Формат: <code>/ban #номер_диалога</code>.",
                )
                return

        if dialog is None:
            await send_owner(
                message,
                "⚠️ Диалог не найден. Проверьте номер диалога или ответьте "
                "на карточку сообщения.",
            )
            return
        if dialog.is_blocked:
            await send_owner(message, f"ℹ️ Диалог #{dialog.id} уже заблокирован.")
            return

        changed = await database.set_blocked(dialog.user_id, True, reason=reason)
        if not changed:
            await send_owner(message, "⚠️ Не удалось изменить статус пользователя.")
            return
        refreshed = await database.get_dialog(dialog.id)
        if refreshed is not None:
            await relay.send_user_blocked_notice(refreshed, True)
        await send_owner(
            message,
            f"🚫 Пользователь диалога #{dialog.id} заблокирован.",
            reply_markup=keyboards.owner_menu_keyboard(),
        )

    @router.message(Command("unban", ignore_case=True))
    async def cmd_unban(message: Message, command: CommandObject) -> None:
        if not is_owner_message(message):
            return
        args = (command.args or "").strip()
        dialog: DialogRecord | None = None

        if message.reply_to_message is not None:
            dialog = await database.resolve_dialog_by_owner_message(
                settings.owner_id,
                message.reply_to_message.message_id,
            )
        if dialog is None and args:
            raw_target = args.split(maxsplit=1)[0]
            if raw_target.startswith("#") and raw_target[1:].isdigit():
                dialog = await database.get_dialog(int(raw_target[1:]))

        if dialog is None:
            await send_owner(
                message,
                "⚠️ Диалог не найден. Проверьте номер диалога или ответьте "
                "на карточку сообщения.",
            )
            return
        if not dialog.is_blocked:
            await send_owner(message, f"ℹ️ Диалог #{dialog.id} не заблокирован.")
            return

        changed = await database.set_blocked(dialog.user_id, False)
        if not changed:
            await send_owner(message, "⚠️ Не удалось изменить статус пользователя.")
            return
        refreshed = await database.get_dialog(dialog.id)
        if refreshed is not None:
            await relay.send_user_blocked_notice(refreshed, False)
        await send_owner(
            message,
            f"✅ Пользователь диалога #{dialog.id} разблокирован.",
            reply_markup=keyboards.owner_menu_keyboard(),
        )

    @router.callback_query(MenuCB.filter())
    async def callback_menu(
        callback: CallbackQuery,
        callback_data: MenuCB,
        state: FSMContext,
    ) -> None:
        if not is_owner_callback(callback):
            await answer(callback, "Нет доступа", alert=True)
            return

        await state.clear()
        action = callback_data.action
        if action == "home":
            await show_panel(callback)
            await answer(callback)
        elif action == "new":
            await show_list(callback, "new", 0)
            await answer(callback)
        elif action == "dialogs":
            await show_list(callback, "dialogs", 0)
            await answer(callback)
        elif action == "users":
            await show_list(callback, "users", 0)
            await answer(callback)
        elif action == "blacklist":
            await show_list(callback, "blacklist", 0)
            await answer(callback)
        elif action == "settings":
            await render(
                callback,
                ui.settings_text(settings),
                keyboards.settings_keyboard(),
                unmap=True,
            )
            await answer(callback)
        else:
            await answer(callback, "Неизвестное действие", alert=True)

    @router.callback_query(ListCB.filter())
    async def callback_list(
        callback: CallbackQuery,
        callback_data: ListCB,
        state: FSMContext,
    ) -> None:
        if not is_owner_callback(callback):
            await answer(callback, "Нет доступа", alert=True)
            return
        await state.clear()
        await show_list(callback, callback_data.section, callback_data.page)
        await answer(callback)

    @router.callback_query(DialogCB.filter())
    async def callback_dialog(
        callback: CallbackQuery,
        callback_data: DialogCB,
        state: FSMContext,
    ) -> None:
        if not is_owner_callback(callback):
            await answer(callback, "Нет доступа", alert=True)
            return

        dialog = await get_dialog_or_none(callback, callback_data.dialog_id)
        if dialog is None:
            return
        action = callback_data.action
        if action not in {"reply", "cancel"}:
            await state.clear()

        if action == "open":
            await database.mark_read(dialog.id)
            refreshed = await database.get_dialog(dialog.id)
            if refreshed is None:
                await answer(callback, ui.dialog_not_found(), alert=True)
                return
            ok = await relay.show_dialog_card(refreshed, edit_message=callback.message)
            await answer(callback, None if ok else "Не удалось открыть диалог")
            return

        if action == "reply":
            await database.mark_read(dialog.id)
            refreshed = await database.get_dialog(dialog.id) or dialog
            await state.set_state(OwnerReplyStates.waiting_for_message)
            await state.update_data(dialog_id=refreshed.id)
            if callback.message is None:
                await state.clear()
                await answer(callback, "Сообщение недоступно", alert=True)
                return
            try:
                prompt = await safe_telegram_call(
                    lambda: callback.message.answer(
                        ui.reply_prompt_text(refreshed),
                        reply_markup=keyboards.reply_prompt_keyboard(refreshed),
                    ),
                    operation="reply_prompt",
                    retries=settings.telegram_max_retries,
                    max_retry_after=settings.floodwait_max_seconds,
                )
            except TelegramAPIError as exc:
                await state.clear()
                logger.warning("Подсказка ответа не доставлена: %s", type(exc).__name__)
                await answer(callback, "Не удалось открыть режим ответа", alert=True)
                return
            await database.map_owner_message(
                settings.owner_id,
                prompt.message_id,
                refreshed.id,
            )
            await answer(callback, "Режим ответа включён")
            return

        if action == "profile":
            await database.mark_read(dialog.id)
            refreshed = await database.get_dialog(dialog.id) or dialog
            await render(
                callback,
                ui.profile_text(refreshed, settings.tzinfo),
                keyboards.profile_keyboard(refreshed),
                dialog_id=refreshed.id,
            )
            await answer(callback)
            return

        if action == "history":
            await database.mark_read(dialog.id)
            refreshed = await database.get_dialog(dialog.id) or dialog
            messages = await database.get_messages(
                refreshed.id,
                settings.history_page_size,
            )
            await render(
                callback,
                ui.history_text(refreshed, messages, settings.tzinfo),
                keyboards.history_keyboard(refreshed),
                dialog_id=refreshed.id,
            )
            await answer(callback)
            return

        if action in {"block", "unblock"}:
            new_state = action == "block"
            if dialog.is_blocked == new_state:
                await relay.show_dialog_card(dialog, edit_message=callback.message)
                await answer(
                    callback,
                    "Пользователь уже заблокирован"
                    if new_state
                    else "Пользователь уже разблокирован",
                )
                return
            await database.set_blocked(dialog.user_id, new_state)
            refreshed = await database.get_dialog(dialog.id) or dialog
            await relay.send_user_blocked_notice(refreshed, new_state)
            await relay.show_dialog_card(refreshed, edit_message=callback.message)
            await answer(
                callback,
                "Пользователь заблокирован"
                if new_state
                else "Пользователь разблокирован",
            )
            return

        if action in {"close", "reopen"}:
            new_status = "closed" if action == "close" else "open"
            if dialog.status == new_status:
                await relay.show_dialog_card(dialog, edit_message=callback.message)
                await answer(
                    callback,
                    "Диалог уже закрыт"
                    if new_status == "closed"
                    else "Диалог уже открыт",
                )
                return
            await database.set_dialog_status(dialog.id, new_status)
            refreshed = await database.get_dialog(dialog.id) or dialog
            await relay.show_dialog_card(refreshed, edit_message=callback.message)
            await answer(
                callback,
                "Диалог закрыт" if new_status == "closed" else "Диалог открыт",
            )
            return

        if action == "refresh":
            await database.mark_read(dialog.id)
            refreshed = await database.get_dialog(dialog.id) or dialog
            ok = await relay.show_dialog_card(refreshed, edit_message=callback.message)
            await answer(callback, None if ok else "Не удалось обновить карточку")
            return

        if action == "cancel":
            await state.clear()
            if callback.message is not None:
                await render(
                    callback,
                    "✖️ Режим ответа отменён.",
                    keyboards.owner_menu_keyboard(),
                    unmap=True,
                )
            await answer(callback, "Отменено")
            return

        await answer(callback, "Неизвестное действие", alert=True)

    @router.callback_query(AdminUserCB.filter())
    async def callback_admin_user(
        callback: CallbackQuery,
        callback_data: AdminUserCB,
        state: FSMContext,
    ) -> None:
        if not is_owner_callback(callback):
            await answer(callback, "Нет доступа", alert=True)
            return
        await state.clear()
        if callback_data.action != "unban":
            await answer(callback, "Неизвестное действие", alert=True)
            return

        dialog = await database.get_dialog_by_user(callback_data.telegram_id)
        if dialog is None:
            await answer(callback, ui.dialog_not_found(), alert=True)
            return
        if not dialog.is_blocked:
            await show_list(callback, "blacklist", callback_data.page)
            await answer(callback, "Пользователь уже разблокирован")
            return

        await database.set_blocked(dialog.user_id, False)
        refreshed = await database.get_dialog(dialog.id) or dialog
        await relay.send_user_blocked_notice(refreshed, False)
        await show_list(callback, "blacklist", callback_data.page)
        await answer(callback, "Пользователь разблокирован")

    @router.message()
    async def handle_owner_message(message: Message, state: FSMContext) -> None:
        if not is_owner_message(message):
            return

        if message.text and message.text.startswith("/"):
            await send_owner(
                message,
                "⚠️ Неизвестная команда. Откройте /menu или /help.",
                reply_markup=keyboards.owner_menu_keyboard(),
            )
            return

        if message.media_group_id:
            try:
                await media_buffer.add(
                    message,
                    lambda messages: flush_owner_album(messages, state),
                )
            except Exception as exc:  # noqa: BLE001 - буфер не должен ронять polling
                logger.error("Ошибка буфера ответа-альбома: %s", type(exc).__name__)
                await send_owner(message, "⚠️ Не удалось обработать альбом.")
            return

        await route_owner_message(message, state)

    return router
