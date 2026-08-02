from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db
from config import KLOD_KLUB_URL, MAIN_CHANNEL, TEST_TELEGRAM_IDS
from scenarios import REGISTRY

logger = logging.getLogger(__name__)

UNKNOWN_SCENARIO_TEXT = "Кажется, эта ссылка уже не работает. Напишите нам, поможем разобраться."

SUBSCRIBE_PROMPT_TEXT = (
    "Гайд бесплатный, пользуйтесь сколько нужно. Но раз я делюсь им просто так - "
    "давайте на баш на баш: подпишитесь на канал {channel_url}, там ещё много "
    "по контенту и нейросетям, и жмите «Готово»."
)
SUBSCRIBE_RETRY_TEXT = "Пока не вижу подписку. Загляните в канал ещё раз и возвращайтесь, жмите «Готово»."

CLUB_INVITE_TEXT_1 = (
    "Раз уж вы наводите порядок в аккаунте через промты, вам наверняка вообще "
    "интересны нейросети. У меня есть отдельный платный канал, Клод-клуб - только "
    "про них. Как реально ускорять контент с ИИ, без хайпа вокруг."
)
CLUB_INVITE_TEXT_2 = (
    "Если хочется разобраться с нейросетями по-настоящему, а не по кусочкам из "
    "разных мест - загляните."
)
CLUB_INVITE_BUTTON = "Посмотреть Клод-клуб"

CLUB_INVITE_DELAY = 2.5
CLUB_INVITE_INTERNAL_DELAY = 1.5


def _channel_url(channel: str) -> str:
    if channel.startswith("http"):
        return channel
    return f"https://t.me/{channel.lstrip('@')}"


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
    await message.answer(scenario["welcome_text"], reply_markup=keyboard)


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
    text = SUBSCRIBE_PROMPT_TEXT.format(channel_url=_channel_url(MAIN_CHANNEL))
    await message.answer(text, reply_markup=keyboard)


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
        await bot.send_message(chat_id, scenario["delivery_text"].format(guide_url=guide_url))
        await db.mark_guide_sent(user_id, scenario_key)
        progress = await db.get_scenario_progress(user_id, scenario_key)

    if scenario.get("offer_klod_klub") and (progress["club_invite_sent_at"] is None or is_test_user):
        await _send_klod_klub_invite(bot, chat_id, user_id, scenario_key)


async def _send_klod_klub_invite(bot: Bot, chat_id: int, user_id: int, scenario_key: str) -> None:
    await asyncio.sleep(CLUB_INVITE_DELAY)
    await bot.send_message(chat_id, CLUB_INVITE_TEXT_1)

    await asyncio.sleep(CLUB_INVITE_INTERNAL_DELAY)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=CLUB_INVITE_BUTTON, url=KLOD_KLUB_URL)]]
    )
    await bot.send_message(chat_id, CLUB_INVITE_TEXT_2, reply_markup=keyboard)

    await db.mark_club_invite_sent(user_id, scenario_key)
