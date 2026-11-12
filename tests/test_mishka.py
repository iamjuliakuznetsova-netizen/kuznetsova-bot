"""Тест выдачи лид-магнита файлом (сценарий mishka): отправка PDF, кэш file_id,
запасные пути (файла нет / file_id протух).

Запуск: python3 tests/test_mishka.py
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
PDF = os.path.join(_tmp, "mishka.pdf")
Path(PDF).write_bytes(b"%PDF-1.4 fake")
os.environ.update({"DB_PATH": os.path.join(_tmp, "t.db"), "BOT_TOKEN": "dummy", "TEST_TELEGRAM_IDS": "", "MISHKA_PDF_FILE": PDF})

from aiogram.exceptions import TelegramBadRequest  # noqa: E402
from aiogram.types import FSInputFile  # noqa: E402

import db  # noqa: E402
import engine  # noqa: E402
from scenarios import REGISTRY  # noqa: E402

SENT: list[tuple] = []


class FakeBot:
    def __init__(self):
        self.reject_file_id = False

    async def get_chat_member(self, chat, user_id):
        return type("M", (), {"status": "member"})()

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        SENT.append(("text", text, reply_markup))

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kw):
        assert os.path.exists(photo.path), photo.path
        SENT.append(("photo", caption, reply_markup))

    async def send_document(self, chat_id, document, **kw):
        if isinstance(document, str):
            if self.reject_file_id:
                raise TelegramBadRequest(method=None, message="Bad Request: wrong file identifier")
            SENT.append(("document-id", document, None))
            return type("Msg", (), {"document": type("D", (), {"file_id": document})()})()
        assert isinstance(document, FSInputFile)
        SENT.append(("document-upload", document.filename, None))
        return type("Msg", (), {"document": type("D", (), {"file_id": "FILEID-1"})()})()


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


def kinds() -> list[str]:
    return [s[0] for s in SENT]


async def run() -> None:
    await db.init_db()
    bot = FakeBot()
    assert "mishka" in REGISTRY

    # первый человек: приветствие -> «Старт» -> картинка с текстом и кнопкой, потом файл
    await engine.handle_start(Msg(bot, 1), "mishka")
    assert SENT[-1][0] == "photo" and "Вы здесь за мишками" in SENT[-1][1]
    SENT.clear()
    await engine.start_button_pressed(Cb(bot, 1), "mishka")
    assert kinds() == ["photo", "document-upload"], f"ожидали картинку+текст, затем файл: {kinds()}"
    assert SENT[0][1].startswith("Файл ваш!")
    rows = SENT[0][2].inline_keyboard
    assert len(rows) == 1 and rows[0][0].text == "Все материалы", "у файловой выдачи нет кнопки-ссылки, только витрина"
    assert SENT[1][1] == "50_слов_мишки_KUZNETSOVA_CREATES.pdf", "имя файла для человека"
    assert (await db.get_scenario_progress(1, "mishka"))["guide_sent_at"] is not None
    print("Выдача: картинка+текст+«Все материалы», затем PDF с нормальным именем - OK")

    # второй человек: файл уходит по сохранённому file_id, без повторной загрузки
    SENT.clear()
    await engine.handle_start(Msg(bot, 2), "mishka")
    SENT.clear()
    await engine.start_button_pressed(Cb(bot, 2), "mishka")
    assert kinds() == ["photo", "document-id"] and SENT[1][1] == "FILEID-1", kinds()
    print("Второй человек получает файл по file_id (без загрузки) - OK")

    # file_id протух -> загружаем заново
    bot.reject_file_id = True
    await engine.handle_start(Msg(bot, 3), "mishka")
    SENT.clear()
    await engine.start_button_pressed(Cb(bot, 3), "mishka")
    assert kinds() == ["photo", "document-upload"], kinds()
    bot.reject_file_id = False
    print("Протухший file_id: файл загружается заново, человек не остаётся без него - OK")

    # заменили файл -> новый ключ кэша -> загрузка заново
    Path(PDF).write_bytes(b"%PDF-1.4 fake, new version, bigger")
    await engine.handle_start(Msg(bot, 4), "mishka")
    SENT.clear()
    await engine.start_button_pressed(Cb(bot, 4), "mishka")
    assert kinds() == ["photo", "document-upload"], "после замены файла кэш не должен отдавать старый"
    print("Заменили PDF: уходит новая версия, а не закэшированная старая - OK")

    # файла на месте нет: не шлём «файл ваш» впустую и не помечаем выдачу состоявшейся
    os.environ["MISHKA_PDF_FILE"] = os.path.join(_tmp, "нет-такого.pdf")
    await engine.handle_start(Msg(bot, 5), "mishka")
    SENT.clear()
    await engine.start_button_pressed(Cb(bot, 5), "mishka")
    assert kinds() == ["text"] and "недоступен" in SENT[0][1], SENT
    assert (await db.get_scenario_progress(5, "mishka"))["guide_sent_at"] is None, "выдача не должна считаться состоявшейся"
    print("Нет файла на сервере: вежливое сообщение, выдача не засчитана (повтор сработает) - OK")


asyncio.run(run())
