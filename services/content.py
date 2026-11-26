"""Извлечение типа и текста из входящих сообщений Telegram."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from aiogram.types import Message


@dataclass(frozen=True, slots=True)
class MessageContent:
    kind: str
    label: str
    text: str
    attachment: bool
    items_count: int = 1


_SINGLE_TYPES: tuple[tuple[str, str], ...] = (
    ("photo", "Фотография"),
    ("video", "Видео"),
    ("video_note", "Видеосообщение"),
    ("voice", "Голосовое сообщение"),
    ("audio", "Аудиофайл"),
    ("animation", "GIF-анимация"),
    ("document", "Документ"),
    ("sticker", "Стикер"),
)

_SENSITIVE_TYPES = ("contact", "location", "venue", "poll", "dice")


def _caption(message: Message) -> str:
    caption = getattr(message, "caption", None)
    return caption.strip() if isinstance(caption, str) and caption.strip() else ""


def _single_type(message: Message) -> tuple[str, str] | None:
    for kind, label in _SINGLE_TYPES:
        if getattr(message, kind, None) is not None:
            return kind, label
    return None


def is_sensitive_message(message: Message) -> bool:
    """Контакт, геолокация и опросы не пересылаются из соображений приватности."""

    return any(getattr(message, kind, None) is not None for kind in _SENSITIVE_TYPES)


def extract_single(message: Message) -> MessageContent | None:
    if is_sensitive_message(message):
        return None
    if message.text is not None and message.text.strip():
        return MessageContent(
            kind="text",
            label="Текст",
            text=message.text.strip(),
            attachment=False,
        )

    type_info = _single_type(message)
    if type_info is None:
        return None
    kind, label = type_info
    return MessageContent(
        kind=kind,
        label=label,
        text=_caption(message),
        attachment=True,
    )


def extract_album(messages: Sequence[Message]) -> MessageContent:
    labels: list[str] = []
    captions: list[str] = []
    for message in messages:
        type_info = _single_type(message)
        if type_info is None:
            continue
        _, label = type_info
        if label not in labels:
            labels.append(label)
        caption = _caption(message)
        if caption and caption not in captions:
            captions.append(caption)

    count = len(messages)
    type_suffix = ", ".join(labels[:3]) if labels else "вложения"
    return MessageContent(
        kind="album",
        label=f"Альбом · {count} {_files_word(count)} ({type_suffix})",
        text="\n".join(captions).strip(),
        attachment=True,
        items_count=count,
    )


def _files_word(count: int) -> str:
    remainder_100 = count % 100
    remainder_10 = count % 10
    if 11 <= remainder_100 <= 14:
        return "файлов"
    if remainder_10 == 1:
        return "файл"
    if 2 <= remainder_10 <= 4:
        return "файла"
    return "файлов"


def preview_text(content: MessageContent, limit: int = 500) -> str:
    text = content.text.strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
