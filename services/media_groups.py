"""Ограниченный буфер для сборки Telegram-альбомов по media_group_id."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from aiogram.types import Message

logger = logging.getLogger(__name__)

GroupKey = tuple[int, str]
FlushCallback = Callable[[list[Message]], Awaitable[None]]


@dataclass(slots=True)
class _Group:
    messages: list[Message] = field(default_factory=list)
    callback: FlushCallback | None = None
    task: asyncio.Task[None] | None = None


class MediaGroupBuffer:
    def __init__(
        self,
        *,
        delay_seconds: float = 0.8,
        max_buffers: int = 500,
        max_items: int = 10,
    ) -> None:
        self._delay = max(0.0, delay_seconds)
        self._max_buffers = max(1, max_buffers)
        self._max_items = max(1, max_items)
        self._groups: OrderedDict[GroupKey, _Group] = OrderedDict()
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def pending_groups(self) -> int:
        return len(self._groups)

    @staticmethod
    def make_key(message: Message) -> GroupKey | None:
        if not message.media_group_id:
            return None
        return message.chat.id, str(message.media_group_id)

    async def add(self, message: Message, callback: FlushCallback) -> bool:
        key = self.make_key(message)
        if key is None:
            return False

        group_to_flush: _Group | None = None
        async with self._lock:
            if self._closed:
                return False

            group = self._groups.get(key)
            if group is None:
                if len(self._groups) >= self._max_buffers:
                    _, group_to_flush = self._groups.popitem(last=False)
                group = _Group(callback=callback)
                self._groups[key] = group
                self._groups.move_to_end(key)
            else:
                self._groups.move_to_end(key)

            if all(
                existing.message_id != message.message_id for existing in group.messages
            ):
                group.messages.append(message)
                if group.callback is None:
                    group.callback = callback

            if group.task is None:
                group.task = asyncio.create_task(
                    self._timer(key),
                    name=f"media-group-{key[0]}-{key[1][:12]}",
                )

            if len(group.messages) >= self._max_items:
                group = self._groups.pop(key, None)
                if group is not None:
                    if (
                        group.task is not None
                        and group.task is not asyncio.current_task()
                    ):
                        group.task.cancel()
                    group_to_flush = group

        if group_to_flush is not None:
            await self._run_callback(group_to_flush)
        return True

    async def _timer(self, key: GroupKey) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return
        await self.flush(key)

    async def flush(self, key: GroupKey) -> None:
        async with self._lock:
            group = self._groups.pop(key, None)
            if group is None:
                return
            current = asyncio.current_task()
            if group.task is not None and group.task is not current:
                group.task.cancel()
        await self._run_callback(group)

    async def _run_callback(self, group: _Group) -> None:
        if not group.messages or group.callback is None:
            return
        messages = sorted(group.messages, key=lambda item: item.message_id)
        try:
            await group.callback(messages)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - буфер не должен ронять polling
            logger.error("Ошибка обработки альбома: %s", type(exc).__name__)

    async def close(self, *, flush: bool = True) -> None:
        async with self._lock:
            self._closed = True
            groups = list(self._groups.values())
            self._groups.clear()
            for group in groups:
                if group.task is not None and group.task is not asyncio.current_task():
                    group.task.cancel()

        if not flush:
            return
        for group in groups:
            await self._run_callback(group)
