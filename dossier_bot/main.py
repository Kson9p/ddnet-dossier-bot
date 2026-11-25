"""Standalone entry point for the separate dossier bot."""

from __future__ import annotations

import asyncio
import contextlib
import html
import json
import logging
import sys
import time
from collections import OrderedDict
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramConflictError, TelegramUnauthorizedError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, ErrorEvent, InlineKeyboardButton, InlineKeyboardMarkup, Message

# Some hosting panels can only run a Python file from the repository.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dossier_bot.config import ConfigError, Settings, load_settings
from dossier_bot.states import AdminFlow, UserFlow
from dossier_bot.stats import DdnetStatsProvider
from dossier_bot.store import DossierStore

log = logging.getLogger(__name__)


class UserActionThrottle:
    """Small per-process cooldown with bounded memory."""

    def __init__(self, seconds: int = 30, max_users: int = 10_000,
                 global_seconds: float = 1.0) -> None:
        self.seconds = seconds
        self.max_users = max_users
        self.last_action: OrderedDict[int, float] = OrderedDict()
        self.global_seconds = global_seconds
        self.last_global_action = 0.0

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        previous = self.last_action.get(user_id)
        if (previous is not None and now - previous < self.seconds) or now - self.last_global_action < self.global_seconds:
            return False
        self.last_action[user_id] = now
        self.last_action.move_to_end(user_id)
        self.last_global_action = now
        while len(self.last_action) > self.max_users:
            self.last_action.popitem(last=False)
        return True


def button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Добавить досье", "d:start")],
        [button("Написать в техподдержку", "s:start")],
        [button("О боте", "about")],
    ])


def cancel_keyboard(*, back: bool = True) -> InlineKeyboardMarkup:
    row = [button("Назад", "d:back")] if back else []
    row.append(button("Отмена", "d:cancel"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Парень", "d:gender:boy"), button("Девушка", "d:gender:girl")],
        [button("Отмена", "d:cancel")],
    ])


def media_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Пропустить фото/видео", "d:skip")],
        [button("Назад", "d:back"), button("Отмена", "d:cancel")],
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Отправить на модерацию", "d:submit")],
        [button("Назад", "d:back"), button("Отмена", "d:cancel")],
    ])


def stats_consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Запросить у DDStats", "stats:fetch")],
        [button("Пропустить запрос", "stats:skip")],
        [button("Назад", "d:back"), button("Отмена", "d:cancel")],
    ])


def review_keyboard(dossier_id: int, *, pending: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if pending:
        rows.append([button("Одобрить", f"d:approve:{dossier_id}"), button("Отклонить", f"d:reject:{dossier_id}")])
    rows.append([button("Удалить досье", f"d:delete:{dossier_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def withdraw_keyboard(dossier_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Удалить / отозвать досье", f"d:withdraw:{dossier_id}")],
    ])


def support_reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Ответить", f"s:reply:{user_id}")],
    ])


def dossier_text(data: dict, *, status: str = "На модерации") -> str:
    category = {"boy": "Парень", "girl": "Девушка"}.get(data.get("gender"), "—")
    media = data.get("media")
    if media is None:
        try:
            media = json.loads(data.get("media_json", "[]"))
        except (TypeError, json.JSONDecodeError):
            media = []
    media_count = len(media) if isinstance(media, list) else 0
    return (
        f"🗂 <b>ДОСЬЕ #{data.get('id', 'черновик')}</b> · {status}\n\n"
        f"Категория: {category}\n"
        f"Ник DDNet: <code>{html.escape(str(data.get('nickname', '')))}</code>\n\n"
        f"Медиа: {media_count} фото/видео\n\n"
        f"{html.escape(str(data.get('description', '')))}\n\n"
        f"📊 {html.escape(str(data.get('stats_text', 'Статистика недоступна.')))}"
    )


async def delete_admin_copies(bot: Bot, owner_id: int, encoded_ids: str) -> bool:
    try:
        ids = json.loads(encoded_ids)
    except (TypeError, json.JSONDecodeError):
        return False
    all_deleted = True
    for message_id in ids:
        try:
            await bot.delete_message(owner_id, int(message_id))
        except TelegramAPIError:
            all_deleted = False
    return all_deleted


def build_admin_router(bot: Bot, settings: Settings, store: DossierStore) -> Router:
    router = Router(name="dossier_admin")
    router.message.filter(F.chat.type == "private", F.from_user.id == settings.owner_id)
    router.callback_query.filter(F.message.chat.type == "private", F.from_user.id == settings.owner_id)

    @router.message(Command("cancel"))
    async def cancel_admin(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Действие отменено.")

    @router.message(AdminFlow.support_reply, F.text)
    async def support_reply(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        recipient = data.get("support_user_id")
        if not isinstance(recipient, int):
            await state.clear()
            await message.answer("Не удалось определить адресата. Нажми «Ответить» под карточкой поддержки.")
            return
        try:
            await bot.copy_message(recipient, message.chat.id, message.message_id)
            await message.answer("✅ Ответ отправлен через бота.")
        except TelegramAPIError:
            await message.answer("Не удалось доставить ответ. Пользователь мог заблокировать бота.")
        await state.clear()

    @router.message(AdminFlow.support_reply)
    async def reject_sensitive_reply(message: Message) -> None:
        await message.answer("Ответ не отправлен. Для защиты приватности поддержка принимает только текст; фото, видео, документы, контакты и геолокацию бот не пересылает. Отправь текст или нажми /cancel.")

    @router.callback_query(F.data.startswith("d:"))
    async def dossier_action(callback: CallbackQuery) -> None:
        parts = (callback.data or "").split(":")
        if len(parts) != 3 or parts[1] not in {"approve", "reject", "delete"}:
            await callback.answer(); return
        try:
            dossier_id = int(parts[2])
        except ValueError:
            await callback.answer("Некорректный номер", show_alert=True); return
        item = await store.get(dossier_id)
        if not item:
            await callback.answer("Досье уже удалено", show_alert=True); return
        action = parts[1]
        if action == "delete":
            await store.delete(dossier_id)
            await callback.answer("Досье удалено", show_alert=True)
            copies_deleted = await delete_admin_copies(bot, settings.owner_id, item["admin_messages_json"])
            if not copies_deleted and callback.message:
                await callback.message.answer("Не удалось удалить все копии из чата модерации. Удали оставшиеся сообщения вручную.")
            return

        status = "approved" if action == "approve" else "rejected"
        await store.set_status(dossier_id, status)
        visible_status = "Одобрено · приватно" if status == "approved" else "Отклонено"
        await callback.answer("Одобрено" if status == "approved" else "Отклонено")
        if callback.message:
            try:
                await callback.message.edit_text(
                    dossier_text(item, status=visible_status),
                    reply_markup=review_keyboard(dossier_id, pending=False),
                )
            except TelegramAPIError:
                pass
        notice = (
            "✅ Досье прошло модерацию и остаётся приватным."
            if status == "approved"
            else "Досье отклонено модератором. Ты можешь удалить его кнопкой в сообщении о подаче."
        )
        try:
            await bot.send_message(item["user_id"], notice, reply_markup=withdraw_keyboard(dossier_id))
        except TelegramAPIError:
            pass

    @router.callback_query(F.data.startswith("s:reply:"))
    async def start_support_reply(callback: CallbackQuery, state: FSMContext) -> None:
        try:
            user_id = int((callback.data or "").split(":", 2)[2])
        except (ValueError, IndexError):
            await callback.answer("Некорректный адресат", show_alert=True); return
        await state.set_state(AdminFlow.support_reply)
        await state.update_data(support_user_id=user_id)
        await callback.answer()
        if callback.message:
            await callback.message.answer("Отправь один текстовый ответ. Медиа и вложения поддержка не пересылает. Отмена: /cancel")

    @router.message(CommandStart())
    async def owner_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Панель владельца нового бота. Обращения поддержки и заявки приходят сюда.")

    @router.message()
    async def owner_hint(message: Message) -> None:
        await message.answer("Чтобы ответить на поддержку, нажми «Ответить» на её карточке. Новые заявки досье имеют отдельные кнопки.")

    return router


def build_user_router(bot: Bot, settings: Settings, store: DossierStore) -> Router:
    router = Router(name="dossier_users")
    router.message.filter(F.chat.type == "private", F.from_user.id != settings.owner_id)
    router.callback_query.filter(F.message.chat.type == "private", F.from_user.id != settings.owner_id)
    stats_provider = DdnetStatsProvider()
    stats_throttle = UserActionThrottle(seconds=30)
    dossier_throttle = UserActionThrottle(seconds=30)
    support_throttle = UserActionThrottle(seconds=15)

    async def send(message: Message, text: str, markup=None) -> None:
        await message.answer(text, reply_markup=markup)

    async def show_preview(message: Message, state: FSMContext) -> None:
        draft = await state.get_data()
        await state.set_state(UserFlow.confirm)
        await send(
            message,
            dossier_text(draft, status="Черновик")
            + "\n\nПодтверди, что информация и медиа относятся к тебе и ты согласен(на) передать их на проверку. До отдельного решения модератора досье не публикуется.",
            confirm_keyboard(),
        )

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await send(message, "👋 Привет! Здесь можно подать досье о себе или обратиться в поддержку.", main_menu())

    @router.message(Command("help"))
    async def help_message(message: Message) -> None:
        await send(message, html.escape(settings.about_text), main_menu())

    @router.message(Command("cancel"))
    async def cancel_command(message: Message, state: FSMContext) -> None:
        await state.clear()
        await send(message, "Черновик удалён.", main_menu())

    @router.callback_query(F.data == "home")
    async def home(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear(); await callback.answer()
        if callback.message:
            await callback.message.answer("Главное меню:", reply_markup=main_menu())

    @router.callback_query(F.data == "about")
    async def about(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message:
            await callback.message.answer(html.escape(settings.about_text), reply_markup=main_menu())

    @router.callback_query(F.data == "d:start")
    async def begin_dossier(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear(); await state.set_state(UserFlow.gender)
        await state.update_data(media=[])
        await callback.answer()
        if callback.message:
            await callback.message.answer("Выбери категорию:", reply_markup=gender_keyboard())

    @router.callback_query(F.data.startswith("d:gender:"))
    async def choose_gender(callback: CallbackQuery, state: FSMContext) -> None:
        if await state.get_state() != UserFlow.gender.state:
            await callback.answer("Начни создание досье заново", show_alert=True); return
        gender = (callback.data or "").rsplit(":", 1)[-1]
        if gender not in {"boy", "girl"}:
            await callback.answer("Неизвестный выбор", show_alert=True); return
        await state.update_data(gender=gender); await state.set_state(UserFlow.nickname)
        await callback.answer()
        if callback.message:
            await callback.message.answer("Напиши свой точный DDNet ник.", reply_markup=cancel_keyboard())

    @router.message(UserFlow.nickname)
    async def get_nickname(message: Message, state: FSMContext) -> None:
        nickname = (message.text or "").strip()
        if not nickname or len(nickname) > 32 or nickname.startswith("/"):
            await send(message, "Введи ник текстом, до 32 символов, или используй /cancel."); return
        await state.update_data(nickname=nickname)
        await state.update_data(
            stats_text="DDraceNetwork: запрос статистики пропущен.\n"
            "KOG: недоступно (нет подтверждённой схемы публичного API).\n"
            "Eternal Gores: недоступно (публичный API не найден)."
        )
        await state.set_state(UserFlow.stats_consent)
        await send(
            message,
            "Для очков рейтинга бот может отправить твой DDNet ник внешнему сервису DDStats. Сервис получит ник. Это необязательно: можно пропустить запрос.",
            stats_consent_keyboard(),
        )

    @router.callback_query(F.data.in_({"stats:fetch", "stats:skip"}))
    async def choose_stats_lookup(callback: CallbackQuery, state: FSMContext) -> None:
        if await state.get_state() != UserFlow.stats_consent.state:
            await callback.answer("Этот шаг уже завершён", show_alert=True); return
        draft = await state.get_data()
        if callback.data == "stats:fetch":
            if stats_throttle.allow(callback.from_user.id):
                result = await stats_provider.fetch(draft.get("nickname", ""))
                await state.update_data(stats_text=result.text)
            else:
                await state.update_data(stats_text="DDraceNetwork: слишком частые запросы, статистика недоступна.\n"
                    "KOG: недоступно (нет подтверждённой схемы публичного API).\n"
                    "Eternal Gores: недоступно (публичный API не найден).")
        await state.set_state(UserFlow.description)
        await callback.answer("Запрошено" if callback.data == "stats:fetch" else "Пропущено")
        if callback.message:
            await callback.message.answer(
                "Коротко расскажи о себе (до 600 символов). Не указывай контакты, адрес или сведения о других людях.",
                reply_markup=cancel_keyboard(),
            )

    @router.message(UserFlow.description)
    async def get_description(message: Message, state: FSMContext) -> None:
        description = (message.text or "").strip()
        if not description or len(description) > 600:
            await send(message, "Нужен текст от 1 до 600 символов."); return
        await state.update_data(description=description, media=[])
        await state.set_state(UserFlow.media)
        await send(message, "Пришли фото или видео о себе (до 10 файлов) либо пропусти шаг. Медиа увидит только модератор.", media_keyboard())

    @router.message(UserFlow.media, F.photo | F.video)
    async def get_media(message: Message, state: FSMContext) -> None:
        draft = await state.get_data(); media = draft.get("media", [])
        if len(media) >= 10:
            await send(message, "Лимит 10 файлов. Пропусти шаг, чтобы продолжить.", media_keyboard()); return
        media.append(
            {"type": "photo", "file_id": message.photo[-1].file_id}
            if message.photo else {"type": "video", "file_id": message.video.file_id}
        )
        await state.update_data(media=media)
        await send(message, f"Файл добавлен ({len(media)}/10). Можно прислать ещё или перейти дальше.", media_keyboard())

    @router.message(UserFlow.media)
    async def unsupported_media(message: Message) -> None:
        await send(message, "Подойдут только фото и видео. Можно пропустить этот шаг.", media_keyboard())

    @router.callback_query(F.data == "d:skip")
    async def skip_media(callback: CallbackQuery, state: FSMContext) -> None:
        if await state.get_state() != UserFlow.media.state:
            await callback.answer("Этот шаг уже завершён", show_alert=True); return
        await callback.answer()
        if callback.message:
            await show_preview(callback.message, state)

    @router.callback_query(F.data == "d:submit")
    async def submit_dossier(callback: CallbackQuery, state: FSMContext) -> None:
        if await state.get_state() != UserFlow.confirm.state:
            await callback.answer("Черновик не найден. Начни заново.", show_alert=True); return
        draft = await state.get_data()
        if (
            draft.get("gender") not in {"boy", "girl"}
            or not isinstance(draft.get("nickname"), str)
            or not isinstance(draft.get("description"), str)
            or not draft["nickname"].strip()
            or not 1 <= len(draft["description"]) <= 600
        ):
            await callback.answer("В черновике не хватает данных. Начни заново.", show_alert=True); return
        if not dossier_throttle.allow(callback.from_user.id):
            await callback.answer("Подожди немного перед следующей заявкой.", show_alert=True); return
        dossier_id = await store.add(callback.from_user.id, draft)
        message_ids: list[int] = []
        delivered = True
        try:
            card = await bot.send_message(
                settings.owner_id, dossier_text({**draft, "id": dossier_id}),
                reply_markup=review_keyboard(dossier_id),
            )
            message_ids.append(card.message_id)
            for item in draft.get("media", []):
                if item["type"] == "photo":
                    sent = await bot.send_photo(settings.owner_id, item["file_id"], caption=f"Медиа к досье #{dossier_id}")
                else:
                    sent = await bot.send_video(settings.owner_id, item["file_id"], caption=f"Медиа к досье #{dossier_id}")
                message_ids.append(sent.message_id)
            await store.set_messages(dossier_id, message_ids)
        except TelegramAPIError as exc:
            log.warning("Could not deliver dossier to owner (%s)", type(exc).__name__)
            await store.delete(dossier_id)
            copies_deleted = await delete_admin_copies(bot, settings.owner_id, json.dumps(message_ids))
            if not copies_deleted:
                await bot.send_message(settings.owner_id, "Не удалось убрать все частично отправленные копии заявки. Проверь сообщения модерации.")
            delivered = False
        await state.clear()
        await callback.answer("Передано на проверку" if delivered else "Не удалось передать")
        if callback.message:
            if delivered:
                await callback.message.answer(
                    "✅ Досье передано модератору. Оно остаётся приватным, пока не принято отдельное решение о публикации.",
                    reply_markup=withdraw_keyboard(dossier_id),
                )
            else:
                await callback.message.answer("Не удалось передать досье модератору. Черновик удалён; попробуй позже.")

    @router.callback_query(F.data == "d:back")
    async def back_dossier(callback: CallbackQuery, state: FSMContext) -> None:
        current = await state.get_state(); await callback.answer()
        if not callback.message:
            return
        if current == UserFlow.nickname.state:
            await state.set_state(UserFlow.gender)
            await callback.message.answer("Выбери категорию:", reply_markup=gender_keyboard())
        elif current == UserFlow.stats_consent.state:
            await state.set_state(UserFlow.nickname)
            await callback.message.answer("Напиши свой точный DDNet ник.", reply_markup=cancel_keyboard())
        elif current == UserFlow.description.state:
            await state.set_state(UserFlow.nickname)
            await callback.message.answer("Напиши свой точный DDNet ник.", reply_markup=cancel_keyboard())
        elif current == UserFlow.media.state:
            await state.set_state(UserFlow.description)
            await callback.message.answer("Коротко расскажи о себе (до 600 символов).", reply_markup=cancel_keyboard())
        elif current == UserFlow.confirm.state:
            await state.set_state(UserFlow.media)
            await callback.message.answer("Пришли фото или видео либо пропусти шаг.", reply_markup=media_keyboard())

    @router.callback_query(F.data == "d:cancel")
    async def cancel_dossier(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear(); await callback.answer("Черновик удалён")
        if callback.message:
            await callback.message.answer("Создание досье отменено.", reply_markup=main_menu())

    @router.callback_query(F.data.startswith("d:withdraw:"))
    async def withdraw(callback: CallbackQuery) -> None:
        try:
            dossier_id = int((callback.data or "").rsplit(":", 1)[-1])
        except ValueError:
            await callback.answer("Некорректный номер", show_alert=True); return
        item = await store.get(dossier_id)
        removed = await store.delete(dossier_id, callback.from_user.id)
        await callback.answer("Досье удалено" if removed else "Досье уже удалено", show_alert=True)
        if removed and item:
            copies_deleted = await delete_admin_copies(bot, settings.owner_id, item["admin_messages_json"])
            if not copies_deleted:
                await bot.send_message(settings.owner_id, f"Не удалось удалить все копии досье #{dossier_id} из чата модерации. Проверь их вручную.")
                if callback.message:
                    await callback.message.answer("Запись удалена. Telegram не позволил убрать все копии из чата модерации; модератору отправлено предупреждение.")
        if removed and callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

    @router.callback_query(F.data == "s:start")
    async def start_support(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear(); await state.set_state(UserFlow.support); await callback.answer()
        if callback.message:
            await callback.message.answer("Напиши сообщение для техподдержки. Можно отправить текст, фото, видео или документ.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button("Отмена", "s:cancel")]]))

    @router.callback_query(F.data == "s:cancel")
    async def cancel_support(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear(); await callback.answer("Отменено")
        if callback.message:
            await callback.message.answer("Обращение отменено.", reply_markup=main_menu())

    @router.message(UserFlow.support, F.text | F.photo | F.video | F.document)
    async def send_support(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return
        if not support_throttle.allow(message.from_user.id):
            await send(message, "Подожди немного перед следующим обращением.", main_menu())
            await state.clear()
            return
        label = await bot.send_message(
            settings.owner_id,
            f"🛟 <b>ТЕХПОДДЕРЖКА</b> · пользователь <code>{message.from_user.id}</code>",
            reply_markup=support_reply_keyboard(message.from_user.id),
        )
        try:
            await bot.copy_message(settings.owner_id, message.chat.id, message.message_id)
        except TelegramAPIError:
            try:
                await bot.delete_message(settings.owner_id, label.message_id)
            except TelegramAPIError:
                pass
            await send(message, "Не удалось доставить обращение. Попробуй ещё раз.")
            return
        await state.clear()
        await send(message, "✅ Обращение доставлено в техподдержку.", main_menu())

    @router.message(UserFlow.support)
    async def support_unsupported(message: Message) -> None:
        await send(message, "Отправь текст, фото, видео или документ. Отмена: /cancel")

    return router


async def run(settings: Settings, *, handle_signals: bool = True) -> None:
    store = DossierStore(settings.database_path)
    bot = Bot(
        settings.token,
        # Keep the HTTP session alive longer than the long-poll request.
        session=AiohttpSession(timeout=40.0),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_admin_router(bot, settings, store))
    dispatcher.include_router(build_user_router(bot, settings, store))

    async def safe_error_handler(event: ErrorEvent) -> bool:
        log.error("Update handler failed (%s)", type(event.exception).__name__)
        try:
            if event.update.callback_query is not None:
                await event.update.callback_query.answer("Временная ошибка. Попробуй ещё раз.", show_alert=True)
            elif event.update.message is not None and event.update.message.chat.type == "private":
                await event.update.message.answer("Временная ошибка. Попробуй ещё раз.")
        except TelegramAPIError:
            pass
        return True

    dispatcher.errors.register(safe_error_handler)
    try:
        log.info("Проверяем подключение к Telegram.")
        me = await bot.me()
        log.info("Telegram подключён: @%s", me.username or "bot")
        await store.open()
        await bot.delete_webhook(drop_pending_updates=False)
        allowed_updates = dispatcher.resolve_used_update_types()
        # Check that Telegram accepts polling without confirming pending updates.
        await bot.get_updates(timeout=1, limit=1, allowed_updates=allowed_updates)
        log.info("Бот @%s принимает обновления. Начинаем long polling.", me.username or "bot")
        polling = asyncio.create_task(dispatcher.start_polling(
            bot, allowed_updates=allowed_updates, polling_timeout=30,
            close_bot_session=False,
            handle_signals=handle_signals, handle_as_tasks=False,
        ))
        try:
            await asyncio.shield(polling)
        finally:
            if not polling.done():
                # Allow start_polling to install its stop event before shutdown.
                await asyncio.sleep(0)
                with contextlib.suppress(RuntimeError):
                    await dispatcher.stop_polling()
            await polling
    finally:
        try:
            await bot.session.close()
        finally:
            await store.close()
            await dispatcher.storage.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | [Досье] %(name)s | %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    try:
        settings = load_settings()
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        log.info("Остановка по Ctrl+C.")
    except TelegramUnauthorizedError:
        log.error("Telegram отклонил DOSSIER_BOT_TOKEN. Проверьте токен в BotFather.")
        return 1
    except TelegramConflictError:
        log.error("Конфликт polling. Проверьте, запущен ли ещё один экземпляр бота досье.")
        return 1
    except TelegramAPIError as exc:
        log.error("Ошибка Telegram (%s).", type(exc).__name__)
        return 1
    except Exception as exc:
        # Avoid putting environment values or filesystem paths from exception
        # messages into shared hosting logs.
        log.error("Бот досье остановлен из-за ошибки (%s).", type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
