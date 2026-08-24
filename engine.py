from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db
from config import KLOD_KLUB_URL, MAIN_CHANNEL, TEST_TELEGRAM_IDS
from scenarios import REGISTRY

logger = logging.getLogger(__name__)

UNKNOWN_SCENARIO_TEXT = "Кажется, эта ссылка уже не работает. Напишите нам, поможем разобраться."

SUBSCRIBE_PROMPT_TEXT = (
    "Гайд полностью бесплатный - пользуйтесь сколько нужно, никаких скрытых счетов через "
    "полгода. Но раз я не жадная, давайте баш на баш: подпишитесь на канал, там ещё в разы "
    "больше по контенту и нейросетям, и жмите «Готово»."
)
SUBSCRIBE_RETRY_TEXT = "Пока не вижу подписку. Может, Telegram притормозил, может - вы. Загляните в канал ещё раз и жмите «Готово»."

CLUB_INVITE_TEXT = (
    "Раз уж вы сюда дошли за промтами, вам явно не всё равно на нейросети - будем считать, "
    "это теперь официально ваша тема. \n"
    "У меня есть отдельный закрытый канал, Клод-клуб, только про них: реальные способы "
    "ускорять контент с ИИ, без охов-ахов вокруг очередной нейросети и без беготни по "
    "десяткам чужих постов и уроков. \n"
    "Загляните, дальше сами решите."
)
CLUB_INVITE_BUTTON = "Посмотреть Клод-клуб"
CLUB_INVITE_DELAY_MINUTES = 20
CLUB_INVITE_POLL_SECONDS = 60


def _channel_url(channel: str) -> str:
    if channel.startswith("http"):
        return channel
    return f"https://t.me/{channel.lstrip('@')}"


async def _send_message(bot: Bot, chat_id: int, text: str, image: str | None = None, reply_markup=None) -> None:
    if image:
        await bot.send_photo(chat_id, FSInputFile(image), caption=text, reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)


async def handle_start(message: Message, scenario_key: str | None) -> None:
    user = message.from_user
    await db.ensure_user(user.id, user.username, user.first_name)

    scenario = REGISTRY.get(scenario_key) if scenario_key else None
    if scenario is None:
        logger.warning("Неизвестный параметр /start: %r (user_id=%s)", scenario_key, user.id)
        await message.answer(UNKNOWN_SCENARIO_TEXT)
        return

    await db.ensure_scenario_progress(user.id, scenario["key"])
    await _show_welcome(message, scenario)


async def _show_welcome(message: Message, scenario: dict) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=scenario["start_button"], callback_data=f"eng:go:{scenario['key']}")]
        ]
    )
    await _send_message(
        message.bot,
        message.chat.id,
        scenario["welcome_text"],
        image=scenario.get("welcome_image"),
        reply_markup=keyboard,
    )


async def start_button_pressed(callback: CallbackQuery, scenario_key: str) -> None:
    scenario = REGISTRY.get(scenario_key)
    if scenario is None:
        logger.warning(
            "Неизвестный сценарий в callback: %r (user_id=%s)", scenario_key, callback.from_user.id
        )
        await callback.message.answer(UNKNOWN_SCENARIO_TEXT)
        return

    if scenario["require_subscription"] and not await db.is_subscribed(callback.from_user.id):
        await _ask_subscription(callback.message, scenario)
        return

    await _deliver(callback.bot, callback.message.chat.id, callback.from_user.id, scenario)


async def _ask_subscription(message: Message, scenario: dict) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться", url=_channel_url(MAIN_CHANNEL))],
            [InlineKeyboardButton(text="Готово", callback_data=f"eng:sub:{scenario['key']}")],
        ]
    )
    await message.answer(SUBSCRIBE_PROMPT_TEXT, reply_markup=keyboard)


async def recheck_subscription(callback: CallbackQuery, scenario_key: str) -> None:
    scenario = REGISTRY.get(scenario_key)
    if scenario is None:
        logger.warning(
            "Неизвестный сценарий в callback: %r (user_id=%s)", scenario_key, callback.from_user.id
        )
        await callback.message.answer(UNKNOWN_SCENARIO_TEXT)
        return

    user_id = callback.from_user.id
    if await _check_membership(callback.bot, user_id):
        await db.mark_subscribed(user_id)
        await _deliver(callback.bot, callback.message.chat.id, user_id, scenario)
    else:
        await callback.message.answer(SUBSCRIBE_RETRY_TEXT)


async def _check_membership(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(MAIN_CHANNEL, user_id)
    except TelegramBadRequest:
        return False
    return member.status in ("member", "administrator", "creator")


async def _deliver(bot: Bot, chat_id: int, user_id: int, scenario: dict) -> None:
    scenario_key = scenario["key"]
    is_test_user = user_id in TEST_TELEGRAM_IDS
    await db.ensure_scenario_progress(user_id, scenario_key)
    progress = await db.get_scenario_progress(user_id, scenario_key)

    if progress["guide_sent_at"] is None or is_test_user:
        guide_url = os.getenv(scenario["guide_url_env"]) or scenario.get("guide_url_placeholder", "")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=scenario.get("delivery_button_text", "Забрать"), url=guide_url)]
            ]
        )
        await _send_message(
            bot, chat_id, scenario["delivery_text"], image=scenario.get("delivery_image"), reply_markup=keyboard
        )
        await db.mark_guide_sent(user_id, scenario_key)

    # Обычным пользователям приглашение в Клод-клуб шлёт фоновая рассылка
    # club_invite_scheduler через CLUB_INVITE_DELAY_MINUTES после выдачи гайда
    # (см. main.py) - так задержка переживает перезапуск бота. Тестовым
    # аккаунтам (TEST_TELEGRAM_IDS) шлём сразу, для удобства проверки.
    if scenario.get("offer_klod_klub") and is_test_user:
        await _send_klod_klub_invite(bot, chat_id, user_id, scenario)


async def _send_klod_klub_invite(bot: Bot, chat_id: int, user_id: int, scenario: dict) -> None:
    text = scenario.get("klod_klub_text", CLUB_INVITE_TEXT)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=CLUB_INVITE_BUTTON, url=KLOD_KLUB_URL)]])
    await _send_message(bot, chat_id, text, image=scenario.get("klod_klub_image"), reply_markup=keyboard)
    await db.mark_club_invite_sent(user_id, scenario["key"])


async def club_invite_scheduler(bot: Bot) -> None:
    """Фоновая задача: раз в минуту проверяет базу и шлёт отложенные приглашения
    в Клод-клуб тем, кому гайд выдан больше CLUB_INVITE_DELAY_MINUTES назад."""
    while True:
        try:
            await _process_pending_club_invites(bot)
        except Exception:
            logger.exception("Ошибка в фоновой рассылке приглашений в Клод-клуб")
        await asyncio.sleep(CLUB_INVITE_POLL_SECONDS)


async def _process_pending_club_invites(bot: Bot) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=CLUB_INVITE_DELAY_MINUTES)).isoformat()
    for row in await db.get_pending_club_invites(cutoff):
        scenario = REGISTRY.get(row["scenario"])
        if scenario is None or not scenario.get("offer_klod_klub"):
            continue
        await _send_klod_klub_invite(bot, row["telegram_id"], row["telegram_id"], scenario)
