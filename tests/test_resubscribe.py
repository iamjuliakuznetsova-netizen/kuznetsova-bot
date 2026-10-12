"""Тест: подписка проверяется заново при каждом нажатии, а не запоминается.

Запуск: python3 tests/test_resubscribe.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

_tmp = tempfile.mkdtemp()
os.environ.update({"DB_PATH": os.path.join(_tmp, "t.db"), "BOT_TOKEN": "dummy", "TEST_TELEGRAM_IDS": ""})

import db  # noqa: E402
import engine  # noqa: E402
from scenarios import REGISTRY  # noqa: E402

KEYS = list(REGISTRY)[:2]
SENT: list[tuple[str, str]] = []


class Member:
    def __init__(self, status):
        self.status = status


class FakeBot:
    def __init__(self):
        self.answer = Member("member")

    async def get_chat_member(self, chat, user_id):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    async def send_message(self, chat_id, text, **kw):
        SENT.append(("text", text))

    async def send_photo(self, chat_id, photo, caption=None, **kw):
        SENT.append(("photo", caption or ""))


class Msg:
    def __init__(self, bot, uid):
        self.bot, self.chat = bot, type("C", (), {"id": uid})()

    async def answer(self, text, **kw):
        await self.bot.send_message(self.chat.id, text)


class Cb:
    def __init__(self, bot, uid, data=""):
        self.bot, self.from_user, self.data = bot, type("U", (), {"id": uid})(), data
        self.message = Msg(bot, uid)

    async def answer(self, text=None):
        pass


def got_prompt() -> bool:
    return any("баш на баш" in text for _, text in SENT)


def got_guide(key: str) -> bool:
    return any(text.startswith("Подборка ваша") or text.startswith("Гайд ваш") or text.startswith("Пост ваш") for _, text in SENT)


async def press_start(bot, uid, key):
    SENT.clear()
    await engine.start_button_pressed(Cb(bot, uid), key)


async def run() -> None:
    await db.init_db()
    bot = FakeBot()
    uid = 500
    await db.ensure_user(uid, "u", "N")
    first, second = KEYS

    await press_start(bot, uid, first)
    assert got_guide(first) and not got_prompt(), SENT
    print("Подписан -> получает гайд - OK")

    # отписался; раньше флаг в базе пропустил бы его, теперь - нет
    bot.answer = Member("left")
    await press_start(bot, uid, second)
    assert got_prompt() and not got_guide(second), "отписавшийся не должен получить второй гайд"
    print("Отписался и пришёл за другим гайдом -> просят подписаться - OK")

    # нажал «Готово», но так и не подписался
    SENT.clear()
    await engine.recheck_subscription(Cb(bot, uid), second)
    assert any("Пока не вижу подписку" in t for _, t in SENT) and not got_guide(second)
    print("«Готово» без подписки -> «пока не вижу» - OK")

    # подписался заново и нажал «Готово»
    bot.answer = Member("member")
    SENT.clear()
    await engine.recheck_subscription(Cb(bot, uid), second)
    assert got_guide(second), SENT
    print("Подписался заново и нажал «Готово» -> гайд - OK")

    # Telegram не ответил (сбой сети) или бот потерял права: не блокируем человека
    from aiogram.exceptions import TelegramBadRequest

    failures = (RuntimeError("сеть"), TelegramBadRequest(method=None, message="Bad Request: member list is inaccessible"))
    for offset, failure in enumerate(failures):
        bot.answer = failure
        await press_start(bot, 501 + offset, first)  # новый человек на каждый случай: повторно гайд не шлётся
        assert got_guide(first) and not got_prompt(), f"при сбое проверки ({failure}) человека пропускаем"
    print("Сбой проверки не блокирует подписчика - OK")


asyncio.run(run())
