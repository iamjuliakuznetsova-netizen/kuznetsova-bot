from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

import engine

router = Router(name="subscription")


@router.callback_query(F.data.startswith("eng:sub:"))
async def cb_check_subscription(callback: CallbackQuery) -> None:
    scenario_key = callback.data.split(":", 2)[2]
    await callback.answer()
    await engine.recheck_subscription(callback, scenario_key)
