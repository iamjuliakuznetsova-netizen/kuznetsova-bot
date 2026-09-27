"""Реконструкция обычного текста из Telegram-объекта rich_message.

Telegram (осень 2026) начал присылать сообщения с нативным форматированием
(например, настоящие нумерованные списки, а не цифры текстом) отдельным
типом контента "rich_message" вместо обычного text/caption -
Message.text и Message.caption в таких сообщениях пустые (None), хотя
сам текст никуда не делся, просто разложен по блокам
(rich_message["blocks"]). aiogram 3.31.0 ничего не знает про этот тип и
не даёт готового способа получить из него обычный текст.

Это молча ломает любую команду, ждущую message.text (например /broadcast) -
если админ использует нативный список Telegram, апдейт получает
"is not handled" без единой строки в трассировке (см. main.py, где
разобрались с ним 27.09.2026). Здесь - минимальная реконструкция текста
из блоков, достаточная для восстановления команд и того форматирования,
которое бот сам же ищет в тексте рассылки (ссылка вида [текст](url))."""
from __future__ import annotations

from typing import Any


def _flatten_inline(parts: Any) -> str:
    """Текст параграфа - либо голая строка, либо список из строк и
    inline-сущностей (bot_command, url и т.п.), каждая со своим полем
    "text" - это и есть то, что реально видно в сообщении."""
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, str):
            chunks.append(part)
        elif isinstance(part, dict):
            chunks.append(str(part.get("text", "")))
    return "".join(chunks)


def _blocks_to_lines(blocks: list[dict]) -> list[str]:
    lines: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "paragraph":
            lines.append(_flatten_inline(block.get("text", "")))
        elif block_type == "list":
            for item in block.get("items", []):
                label = item.get("label", "")
                inner = "\n".join(_blocks_to_lines(item.get("blocks", [])))
                lines.append(f"{label} {inner}".strip())
        # Другие типы блоков (цитата, код и т.п.) пока не встречались в
        # реальных сообщениях - пропускаем, а не роняем всё сообщение.
    return lines


def rich_message_to_text(rich_message: dict) -> str:
    """Собирает из rich_message["blocks"] обычный многострочный текст -
    приблизительно то же, что было бы в message.text, отправь это
    сообщение без нативного форматирования Telegram."""
    return "\n".join(_blocks_to_lines(rich_message.get("blocks", [])))
