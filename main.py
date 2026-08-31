from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

import db
from config import BOT_TOKEN
from engine import club_invite_scheduler
from handlers import admin, start, subscription


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Заполните .env (см. .env.example)")

    await db.init_db()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(subscription.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен, ждём сообщения...")

    asyncio.create_task(club_invite_scheduler(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
