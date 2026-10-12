"""Тест на строку "сейчас подписаны на канал" в /stats.

Запуск: python3 tests/test_subscription_audit.py
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
os.environ.update({"DB_PATH": os.path.join(_tmp, "t.db"), "BOT_TOKEN": "dummy", "ADMIN_TELEGRAM_IDS": "999"})

from aiogram.exceptions import TelegramBadRequest  # noqa: E402

import db  # noqa: E402
import subscription_audit as audit  # noqa: E402
from handlers import admin  # noqa: E402


class Member:
    def __init__(self, status, is_member=None):
        self.status = status
        self.is_member = is_member


class FakeBot:
    def __init__(self, statuses):
        self.statuses = statuses
        self.calls = 0

    async def get_chat_member(self, chat, user_id):
        self.calls += 1
        value = self.statuses[user_id]
        if isinstance(value, Exception):
            raise value
        return value


class FakeMessage:
    def __init__(self, bot):
        self.from_user = type("U", (), {"id": 999})()
        self.bot = bot
        self.sent: list[str] = []

    async def answer(self, text, **kwargs):
        self.sent.append(text)


def bad_request(text):
    return TelegramBadRequest(method=None, message=text)


async def run() -> None:
    await db.init_db()
    # сценарий a: 1,2,3,4; сценарий b: 1,5,6,7 (1 получил оба гайда)
    for scenario, users in (("a", (1, 2, 3, 4)), ("b", (1, 5, 6, 7))):
        for uid in users:
            await db.ensure_user(uid, "u", "N")
            await db.ensure_scenario_progress(uid, scenario)
            await db.mark_guide_sent(uid, scenario)

    statuses = {
        1: Member("member"),
        2: Member("left"),
        3: Member("kicked"),
        4: Member("administrator"),
        5: RuntimeError("сеть"),
        6: bad_request("Bad Request: user not found"),
        7: Member("restricted", is_member=True),
    }
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    bot = FakeBot(statuses)
    ids = sorted({uid for _, uid in await db.scenario_receivers()})
    result = await audit.run_audit(bot, ids, sleep=fake_sleep)

    assert result.states == {1: True, 2: False, 3: False, 4: True, 6: False, 7: True}, result.states
    assert result.unknown == {5}, "сетевой сбой = не удалось проверить, а не 'отписан'"
    assert bot.calls == 7 and len(sleeps) == 7 and all(s >= 0.05 for s in sleeps), "не быстрее 20 запросов в секунду"
    assert result.saved, "результат проверки должен сохраняться в базе"
    print("Статусы, неизвестные, лимит 20 запросов/сек, сохранение - OK")

    rows = await db.scenario_stats()
    text = audit.build_stats_text(await db.total_users(), rows, await db.scenario_receivers(), result, None, {})
    assert "• a: заходили 4, получили гайд 4, сейчас подписаны на канал 2 (50%)" in text, text
    assert "• b: заходили 4, получили гайд 4, сейчас подписаны на канал 2 (67%), не удалось проверить 1" in text, text
    assert "первая проверка" in text
    print("Строка по сценариям и процент (с учётом непроверенных) - OK")

    # вторая проверка: 1 отписался, 2 вернулся
    statuses[1] = Member("left")
    statuses[2] = Member("member")
    statuses[5] = Member("member")
    await asyncio.sleep(0.01)  # другой checked_at
    second = await audit.run_audit(FakeBot(statuses), ids, sleep=fake_sleep)
    prev_at = await db.previous_check_run(second.checked_at)
    assert prev_at == result.checked_at
    text2 = audit.build_stats_text(
        await db.total_users(), rows, await db.scenario_receivers(), second, prev_at, await db.subscription_states(prev_at)
    )
    assert "отписались 1, вернулись 1" in text2, text2
    print("Динамика между проверками (1 ушёл, 1 вернулся) - OK")

    # бот потерял права админа: Telegram отвечает BadRequest на всех -> НЕ "все отписались"
    broken = FakeBot({uid: bad_request("Bad Request: member list is inaccessible") for uid in ids})
    third = await audit.run_audit(broken, ids, sleep=fake_sleep)
    assert third.suspicious and not third.saved and not third.states, "при массовых сбоях ничего не сохраняем"
    text3 = audit.build_stats_text(await db.total_users(), rows, await db.scenario_receivers(), third, None, {})
    assert "⚠️" in text3 and "администратором канала" in text3
    assert await db.previous_check_run("9999") == second.checked_at, "мусорный прогон не попал в историю"
    print("Потеря прав админа не превращается в '0% подписаны' и не пишется в историю - OK")

    # сам /stats: доступ только админу, два сообщения (ожидание + итог)
    outsider = FakeMessage(FakeBot(statuses))
    outsider.from_user = type("U", (), {"id": 1})()
    await admin.cmd_stats(outsider)
    assert outsider.sent == []

    original_sleep = audit.REQUEST_DELAY_SECONDS
    audit.REQUEST_DELAY_SECONDS = 0
    try:
        message = FakeMessage(FakeBot(statuses))
        await admin.cmd_stats(message)
    finally:
        audit.REQUEST_DELAY_SECONDS = original_sleep
    assert len(message.sent) == 2 and "Проверяю подписку" in message.sent[0], message.sent
    assert "сейчас подписаны на канал" in message.sent[1]
    print("/stats: только для админа, ожидание + итог - OK")


asyncio.run(run())
