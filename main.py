from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

import db
from config import BOT_TOKEN
from engine import club_invite_scheduler
from handlers import admin, start, subscription
from http_session import ResilientAiohttpSession
from rich_text import rich_message_to_text

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Заполните .env (см. .env.example)")

    await db.init_db()

    bot = Bot(BOT_TOKEN, session=ResilientAiohttpSession())
    dp = Dispatcher()

    @dp.update.outer_middleware()
    async def backfill_rich_message_text(handler, event, data):
        """27.09.2026: Telegram теперь шлёт сообщения с нативным
        форматированием (например, настоящие нумерованные списки) отдельным
        типом rich_message - message.text/caption там пустые, поэтому
        /broadcast (и любая другая команда) молча не срабатывает, если
        админ воспользовался таким форматированием. Реконструируем текст из
        rich_message.blocks (см. rich_text.py) и подставляем его в
        message.text ДО фильтров - дальше всё работает как обычно. Нашли и
        починили сначала в capcut-bazaart-bot, переносим сюда тем же кодом."""
        message = event.message or event.edited_message
        if message is not None and message.text is None and message.caption is None:
            dump = message.model_dump(exclude_none=True)
            rich = dump.get("rich_message")
            if rich:
                reconstructed = rich_message_to_text(rich)
                logger.info(
                    "rich_message от %s реконструирован в текст (%d симв.)",
                    message.from_user.id if message.from_user else None,
                    len(reconstructed),
                )
                try:
                    message.text = reconstructed
                except Exception:
                    object.__setattr__(message, "text", reconstructed)
        return await handler(event, data)

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(subscription.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен, ждём сообщения...")

    asyncio.create_task(club_invite_scheduler(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
