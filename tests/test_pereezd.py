"""Тест сценария pereezd и отправки без картинки (если файла ещё нет в assets/).

Запуск: python3 tests/test_pereezd.py
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

_tmp = tempfile.mkdtemp()
os.environ.update({"DB_PATH": os.path.join(_tmp, "t.db"), "BOT_TOKEN": "dummy", "TEST_TELEGRAM_IDS": "111"})
os.environ["PEREEZD_GUIDE_URL"] = "https://kuznetsova.studio/claude-backup"

import db  # noqa: E402
import engine  # noqa: E402
from scenarios import REGISTRY  # noqa: E402

SENT: list[tuple[str, str, object]] = []


class FakeBot:
    async def get_chat_member(self, chat, user_id):
        return type("M", (), {"status": "member"})()

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        SENT.append(("text", text, reply_markup))

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kw):
        assert os.path.exists(photo.path), f"отправка фото несуществующего файла {photo.path}"
        SENT.append(("photo", caption, reply_markup))


class Msg:
    def __init__(self, bot, uid):
        self.bot, self.from_user, self.chat = bot, type("U", (), {"id": uid, "username": "u", "first_name": "N"})(), type("C", (), {"id": uid})()

    async def answer(self, text, reply_markup=None, **kw):
        await self.bot.send_message(self.chat.id, text, reply_markup=reply_markup)


class Cb:
    def __init__(self, bot, uid):
        self.bot, self.from_user, self.data = bot, type("U", (), {"id": uid})(), ""
        self.message = Msg(bot, uid)

    async def answer(self, text=None):
        pass


async def run() -> None:
    await db.init_db()
    bot = FakeBot()
    assert "pereezd" in REGISTRY
    club_image = "assets/pereezd_klodklub.png"
    created = False
    if os.path.exists(club_image):
        raise SystemExit("assets/pereezd_klodklub.png уже есть - тест на отсутствие картинки не имеет смысла, уберите/переименуйте файл")

    # обычный человек: приветствие с картинкой -> «Старт» -> выдача с двумя кнопками
    await engine.handle_start(Msg(bot, 222), "pereezd")
    assert SENT[-1][0] == "photo" and "Месяцы работы в Claude" in SENT[-1][1], SENT[-1]
    SENT.clear()
    await engine.start_button_pressed(Cb(bot, 222), "pereezd")
    kind, text, kb = SENT[0]
    assert kind == "photo" and text.startswith("Инструкция ваша"), SENT[0]
    assert kb.inline_keyboard[0][0].text == "Забрать инструкцию"
    assert kb.inline_keyboard[0][0].url == "https://kuznetsova.studio/claude-backup"
    assert kb.inline_keyboard[1][0].text == "Все материалы"
    assert len(SENT) == 1, "обычному человеку приглашение сразу не шлём (через 20 минут)"
    print("Приветствие + выдача: картинки, кнопка на инструкцию, «Все материалы» - OK")

    # тестовый аккаунт: приглашение сразу; картинки клуба нет -> текстом, без падения
    SENT.clear()
    await engine.start_button_pressed(Cb(bot, 111), "pereezd")
    club = [s for s in SENT if "закрытый канал, Клод-клуб" in (s[1] or "")]
    assert len(club) == 1 and club[0][0] == "text", f"без файла приглашение должно уйти текстом: {SENT}"
    assert club[0][1].startswith("Если инструкция пригодилась"), "должен быть свой текст, а не общий"
    print("Приглашение без картинки уходит текстом (не падает) - OK")

    # появился файл - то же приглашение уходит уже с картинкой
    shutil.copy("assets/pereezd_guide.webp", club_image)
    created = True
    try:
        SENT.clear()
        await engine.start_button_pressed(Cb(bot, 111), "pereezd")
        club = [s for s in SENT if "закрытый канал, Клод-клуб" in (s[1] or "")]
        assert len(club) == 1 and club[0][0] == "photo", f"с файлом приглашение должно уйти с картинкой: {SENT}"
        print("Положили картинку в assets/ - приглашение уходит с ней, код менять не нужно - OK")
    finally:
        if created:
            os.remove(club_image)

    # остальные сценарии не задеты
    for i, key in enumerate(k for k in REGISTRY if k != "pereezd"):
        uid = 900 + i
        SENT.clear()
        await engine.handle_start(Msg(bot, uid), key)
        await engine.start_button_pressed(Cb(bot, uid), key)
        assert any(s[2] is not None and len(s[2].inline_keyboard) == 2 for s in SENT), f"{key}: выдача сломалась"
    print(f"Остальные {len(REGISTRY) - 1} сценариев выдают гайд как раньше - OK")


asyncio.run(run())
