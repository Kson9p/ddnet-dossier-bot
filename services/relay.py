"""Двусторонняя доставка сообщений между пользователем и владельцем."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
)
from aiogram.types import LinkPreviewOptions, Message

import keyboards
import ui
from config import Settings
from database import Database, DialogRecord
from services.content import (
    MessageContent,
    extract_album,
    extract_single,
    is_sensitive_message,
    preview_text,
)
from services.telegram import safe_telegram_call

logger = logging.getLogger(__name__)
T = TypeVar("T")


class RelayService:
    def __init__(self, bot: Bot, database: Database, settings: Settings) -> None:
        self._bot = bot
        self._db = database
        self._settings = settings

    async def _call(
        self,
        factory: Callable[[], Awaitable[T]],
        operation: str,
    ) -> T:
        return await safe_telegram_call(
            factory,
            operation=operation,
            retries=self._settings.telegram_max_retries,
            max_retry_after=self._settings.floodwait_max_seconds,
        )

    async def _send_owner_card(
        self,
        dialog: DialogRecord,
        content: MessageContent,
        received_at: int,
    ) -> Message | None:
        text = ui.new_message_card(dialog, content, received_at, self._settings.tzinfo)
        try:
            sent = await self._call(
                lambda: self._bot.send_message(
                    chat_id=self._settings.owner_id,
                    text=text,
                    reply_markup=keyboards.dialog_card_keyboard(dialog),
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
                "send_owner_card",
            )
        except TelegramForbiddenError:
            logger.error("Карточка не доставлена: владелец недоступен для бота")
            return None
        except TelegramAPIError as exc:
            logger.error(
                "Не удалось отправить карточку владельцу: %s", type(exc).__name__
            )
            return None

        await self._db.map_owner_message(
            self._settings.owner_id,
            sent.message_id,
            dialog.id,
        )
        return sent

    async def deliver_user_message(
        self,
        message: Message,
        dialog: DialogRecord,
        content: MessageContent,
    ) -> bool:
        record = await self._db.record_incoming(
            dialog.id,
            content.kind,
            preview_text(content) or None,
            count=1,
        )
        refreshed = await self._db.get_dialog(dialog.id)
        if refreshed is None:
            return False

        card = await self._send_owner_card(refreshed, content, record.created_at)
        if card is None:
            return False

        if content.attachment:
            delivered = await self._copy_user_messages_to_owner([message], refreshed)
            if not delivered:
                await self._notify_owner_error(
                    ui.delivery_failed_owner_text(refreshed.id)
                )
            return delivered

        if len(content.text) > ui.CARD_TEXT_LIMIT:
            delivered = await self._copy_user_messages_to_owner([message], refreshed)
            if not delivered:
                await self._notify_owner_error(
                    ui.delivery_failed_owner_text(refreshed.id)
                )
            return delivered

        return True

    async def deliver_user_album(self, messages: Sequence[Message]) -> bool:
        messages = sorted(messages, key=lambda item: item.message_id)
        if not messages:
            return False
        first = messages[0]
        if first.from_user is None:
            return False

        dialog = await self._db.get_dialog_by_user(first.from_user.id)
        if dialog is None:
            dialog = await self._db.get_or_create_dialog(
                first.from_user.id,
                first.from_user.full_name,
                first.from_user.username,
            )
        content = extract_album(messages)
        record = await self._db.record_incoming(
            dialog.id,
            content.kind,
            preview_text(content) or None,
            count=len(messages),
        )
        refreshed = await self._db.get_dialog(dialog.id)
        if refreshed is None:
            return False

        card = await self._send_owner_card(refreshed, content, record.created_at)
        if card is None:
            return False

        delivered = await self._copy_user_album_to_owner(messages, refreshed)
        if not delivered:
            await self._notify_owner_error(ui.delivery_failed_owner_text(refreshed.id))
        return delivered

    async def _copy_user_messages_to_owner(
        self,
        messages: Sequence[Message],
        dialog: DialogRecord,
    ) -> bool:
        if not messages:
            return False
        copied_ids: list[int] = []
        for message in messages:
            try:
                copied = await self._call(
                    lambda item=message: self._bot.copy_message(
                        chat_id=self._settings.owner_id,
                        from_chat_id=item.chat.id,
                        message_id=item.message_id,
                    ),
                    "copy_user_message",
                )
            except TelegramForbiddenError:
                logger.error("Вложение не доставлено: владелец недоступен для бота")
                return False
            except TelegramAPIError as exc:
                logger.warning(
                    "Не удалось скопировать вложение пользователя: %s",
                    type(exc).__name__,
                )
                continue
            copied_ids.append(copied.message_id)

        if copied_ids:
            await self._db.map_owner_messages(
                self._settings.owner_id,
                copied_ids,
                dialog.id,
            )
        return len(copied_ids) == len(messages)

    async def _copy_user_album_to_owner(
        self,
        messages: Sequence[Message],
        dialog: DialogRecord,
    ) -> bool:
        first = messages[0]
        try:
            copied = await self._call(
                lambda: self._bot.copy_messages(
                    chat_id=self._settings.owner_id,
                    from_chat_id=first.chat.id,
                    message_ids=[message.message_id for message in messages],
                ),
                "copy_user_album",
            )
        except TelegramForbiddenError:
            logger.error("Альбом не доставлен: владелец недоступен для бота")
            return False
        except TelegramAPIError as exc:
            logger.warning(
                "Не удалось скопировать альбом целиком (%s), пробую по одному",
                type(exc).__name__,
            )
            return await self._copy_user_messages_to_owner(messages, dialog)
        else:
            await self._db.map_owner_messages(
                self._settings.owner_id,
                [item.message_id for item in copied],
                dialog.id,
            )
            return True

    async def deliver_owner_message(
        self,
        message: Message,
        dialog: DialogRecord,
    ) -> bool:
        if message.from_user is None or message.from_user.id != self._settings.owner_id:
            return False

        if is_sensitive_message(message):
            await self.send_owner_text(ui.sensitive_owner_text())
            return False

        content = extract_single(message)
        if content is None:
            await self.send_owner_text(ui.unsupported_owner_text())
            return False

        try:
            await self._call(
                lambda: self._bot.copy_message(
                    chat_id=dialog.user_id,
                    from_chat_id=self._settings.owner_id,
                    message_id=message.message_id,
                ),
                "copy_owner_message",
            )
        except TelegramForbiddenError:
            logger.warning("Ответ не доставлен: пользователь недоступен")
            await self._notify_owner_error(ui.user_blocked_bot_owner_text(dialog.id))
            return False
        except TelegramAPIError as exc:
            logger.warning("Ответ не доставлен: %s", type(exc).__name__)
            await self._notify_owner_error(ui.user_blocked_bot_owner_text(dialog.id))
            return False

        await self._db.record_outgoing(
            dialog.id,
            content.kind,
            preview_text(content) or None,
        )
        return True

    async def deliver_owner_album(
        self,
        messages: Sequence[Message],
        dialog: DialogRecord,
    ) -> bool:
        messages = sorted(messages, key=lambda item: item.message_id)
        if not messages:
            return False
        first = messages[0]
        if first.from_user is None or first.from_user.id != self._settings.owner_id:
            return False
        if any(is_sensitive_message(message) for message in messages):
            await self.send_owner_text(ui.sensitive_owner_text())
            return False

        delivered = False
        try:
            await self._call(
                lambda: self._bot.copy_messages(
                    chat_id=dialog.user_id,
                    from_chat_id=self._settings.owner_id,
                    message_ids=[message.message_id for message in messages],
                ),
                "copy_owner_album",
            )
            delivered = True
        except TelegramForbiddenError:
            logger.warning("Ответ-альбом не доставлен: пользователь недоступен")
            await self._notify_owner_error(ui.user_blocked_bot_owner_text(dialog.id))
            return False
        except TelegramAPIError as exc:
            logger.warning(
                "Не удалось отправить альбом целиком (%s), пробую по одному",
                type(exc).__name__,
            )
            for message in messages:
                try:
                    await self._call(
                        lambda item=message: self._bot.copy_message(
                            chat_id=dialog.user_id,
                            from_chat_id=self._settings.owner_id,
                            message_id=item.message_id,
                        ),
                        "copy_owner_message",
                    )
                    delivered = True
                except TelegramAPIError as item_exc:
                    logger.warning(
                        "Часть ответа не доставлена: %s",
                        type(item_exc).__name__,
                    )

        if not delivered:
            await self._notify_owner_error(ui.user_blocked_bot_owner_text(dialog.id))
            return False

        content = extract_album(messages)
        await self._db.record_outgoing(
            dialog.id,
            "album",
            preview_text(content) or None,
        )
        return True

    async def show_dialog_card(
        self,
        dialog: DialogRecord,
        *,
        edit_message: Message | None = None,
    ) -> bool:
        latest = await self._db.get_latest_message(dialog.id)
        text = ui.dialog_card_text(dialog, latest, self._settings.tzinfo)
        keyboard = keyboards.dialog_card_keyboard(dialog)

        if edit_message is not None:
            try:
                await self._call(
                    lambda: self._bot.edit_message_text(
                        chat_id=self._settings.owner_id,
                        message_id=edit_message.message_id,
                        text=text,
                        reply_markup=keyboard,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    ),
                    "edit_dialog_card",
                )
            except TelegramBadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    logger.warning("Не удалось изменить карточку, отправляю новую")
                else:
                    await self._db.map_owner_message(
                        self._settings.owner_id,
                        edit_message.message_id,
                        dialog.id,
                    )
                    return True
            except TelegramForbiddenError:
                logger.error("Карточка не обновлена: владелец недоступен для бота")
                return False
            except TelegramAPIError as exc:
                logger.warning("Не удалось изменить карточку: %s", type(exc).__name__)
            else:
                await self._db.map_owner_message(
                    self._settings.owner_id,
                    edit_message.message_id,
                    dialog.id,
                )
                return True

        try:
            sent = await self._call(
                lambda: self._bot.send_message(
                    chat_id=self._settings.owner_id,
                    text=text,
                    reply_markup=keyboard,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
                "send_dialog_card",
            )
        except TelegramAPIError as exc:
            logger.error("Не удалось отправить карточку: %s", type(exc).__name__)
            return False

        await self._db.map_owner_message(
            self._settings.owner_id,
            sent.message_id,
            dialog.id,
        )
        return True

    async def send_owner_text(self, text: str) -> bool:
        try:
            await self._call(
                lambda: self._bot.send_message(
                    chat_id=self._settings.owner_id,
                    text=text,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
                "send_owner_text",
            )
        except TelegramAPIError as exc:
            logger.warning(
                "Служебное сообщение владельцу не доставлено: %s", type(exc).__name__
            )
            return False
        return True

    async def _notify_owner_error(self, text: str) -> None:
        await self.send_owner_text(text)

    async def send_user_notice(self, dialog: DialogRecord, text: str) -> bool:
        try:
            await self._call(
                lambda: self._bot.send_message(
                    chat_id=dialog.user_id,
                    text=text,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
                "send_user_notice",
            )
        except TelegramForbiddenError:
            logger.warning("Уведомление не доставлено: пользователь недоступен")
            return False
        except TelegramAPIError as exc:
            logger.warning(
                "Уведомление не доставлено: %s",
                type(exc).__name__,
            )
            return False
        return True

    async def send_user_blocked_notice(
        self, dialog: DialogRecord, blocked: bool
    ) -> None:
        text = ui.banned_notice() if blocked else ui.unbanned_notice()
        await self.send_user_notice(dialog, text)
