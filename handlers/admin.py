from __future__ import annotations

import asyncio
import logging
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db
from config import ADMIN_TELEGRAM_IDS

logger = logging.getLogger(__name__)
router = Router(name="admin")

BUTTON_LINE_RE = re.compile(r"\n?\[(.+?)\]\((https?://\S+)\)\s*$")
SEND_DELAY_SECONDS = 0.05  # ~20 сообщений в секунду, с запасом от лимитов Telegram

# Черновики рассылки между командой /broadcast и подтверждением - в памяти,
# не в базе: живут недолго (пока админ не подтвердит или не отменит).
_pending_broadcasts: dict[int, dict] = {}


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_TELEGRAM_IDS


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    total = await db.total_users()
    rows = await db.scenario_stats()

    lines = [f"👥 Всего пользователей бота: {total}", ""]
    if not rows:
        lines.append("Пока никто не заходил ни в один сценарий.")
    for row in rows:
        lines.append(f"• {row['scenario']}: заходили {row['started']}, получили гайд {row['delivered']}")
    await message.answer("\n".join(lines))


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    text = (message.html_text or message.caption or "")
    text = re.sub(r"^/broadcast(@\w+)?\s*", "", text, count=1).strip()

    button = None
    match = BUTTON_LINE_RE.search(text)
    if match:
        button = (match.group(1), match.group(2))
        text = text[: match.start()].rstrip()

    if not text and not message.photo:
        await message.answer(
            "Использование:\n"
            "/broadcast Текст рассылки\n\n"
            "Можно приложить фото - тогда текст пишите в подписи к фото.\n"
            "Кнопка со ссылкой - последней строкой в формате "
            "[Текст кнопки](https://ссылка)"
        )
        return

    photo_file_id = message.photo[-1].file_id if message.photo else None
    total = await db.total_users()

    _pending_broadcasts[message.from_user.id] = {
        "text": text,
        "photo_file_id": photo_file_id,
        "button": button,
    }

    preview_keyboard = None
    if button:
        preview_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button[0], url=button[1])]])

    await message.answer("Вот как будет выглядеть рассылка 👇")
    if photo_file_id:
        await message.answer_photo(photo_file_id, caption=text or None, reply_markup=preview_keyboard)
    else:
        await message.answer(text, reply_markup=preview_keyboard)

    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Разослать всем ({total})", callback_data="bcast:send")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bcast:cancel")],
        ]
    )
    await message.answer(f"Отправить это {total} пользователям?", reply_markup=confirm_keyboard)


@router.callback_query(F.data == "bcast:cancel")
async def cb_broadcast_cancel(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    _pending_broadcasts.pop(callback.from_user.id, None)
    await callback.answer("Отменено")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data == "bcast:send")
async def cb_broadcast_send(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return

    draft = _pending_broadcasts.pop(callback.from_user.id, None)
    await callback.answer()
    if draft is None:
        await callback.message.answer("Черновик рассылки не найден (истёк или уже отправлен). Наберите /broadcast заново.")
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Начинаю рассылку...")

    keyboard = None
    if draft["button"]:
        btn_text, btn_url = draft["button"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=btn_url)]])

    user_ids = await db.list_all_user_ids()
    sent, failed = 0, 0

    for user_id in user_ids:
        try:
            await _send_one(callback.bot, user_id, draft, keyboard)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await _send_one(callback.bot, user_id, draft, keyboard)
                sent += 1
            except Exception:
                failed += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception:
            logger.exception("Не удалось разослать сообщение пользователю %s", user_id)
            failed += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)

    await callback.message.answer(
        f"Готово ✅\nОтправлено: {sent}\nНе удалось (заблокировали бота или ошибка): {failed}"
    )


async def _send_one(bot, user_id: int, draft: dict, keyboard) -> None:
    if draft["photo_file_id"]:
        await bot.send_photo(user_id, draft["photo_file_id"], caption=draft["text"] or None, reply_markup=keyboard)
    else:
        await bot.send_message(user_id, draft["text"], reply_markup=keyboard)
