from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

import engine

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    await engine.handle_start(message, command.args)


@router.callback_query(F.data.startswith("eng:go:"))
async def cb_start_button(callback: CallbackQuery) -> None:
    scenario_key = callback.data.split(":", 2)[2]
    await callback.answer()
    await engine.start_button_pressed(callback, scenario_key)
