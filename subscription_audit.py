"""Сколько из получивших гайд до сих пор подписаны на канал (для /stats).

Для каждого человека - bot.get_chat_member(MAIN_CHANNEL, user_id); результат
каждого прогона сохраняется в subscription_checks, чтобы в следующем /stats
было видно, кто отписался или вернулся с прошлой проверки.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

import db
from config import MAIN_CHANNEL

logger = logging.getLogger(__name__)

REQUESTS_PER_SECOND = 20
REQUEST_DELAY_SECONDS = 1 / REQUESTS_PER_SECOND
# Если не удалось проверить больше такой доли людей - данным верить нельзя
# (например, бот перестал быть админом канала), историю такими данными не
# засоряем и результат не сохраняем.
MAX_UNKNOWN_SHARE = 0.3

_ACTIVE = {"member", "administrator", "creator"}
_GONE = {"left", "kicked"}


@dataclass
class AuditResult:
    checked_at: str
    states: dict[int, bool] = field(default_factory=dict)
    unknown: set[int] = field(default_factory=set)
    saved: bool = False

    @property
    def suspicious(self) -> bool:
        total = len(self.states) + len(self.unknown)
        return total > 0 and len(self.unknown) / total > MAX_UNKNOWN_SHARE


async def check_subscription(bot: Bot, user_id: int) -> bool | None:
    """True - подписан, False - нет, None - проверить не удалось.

    Нельзя считать любой BadRequest за "не подписан": если бот потеряет права админа в канале, Telegram ответит
    "member list is inaccessible", и вся аудитория выглядела бы отписанной."""
    try:
        member = await bot.get_chat_member(MAIN_CHANNEL, user_id)
    except TelegramBadRequest as error:
        text = str(error).lower()
        if "user not found" in text or "participant_id_invalid" in text:
            return False
        logger.warning("Не удалось проверить подписку %s: %s", user_id, error)
        return None
    except Exception as error:
        logger.warning("Не удалось проверить подписку %s: %s", user_id, error)
        return None

    if member.status in _ACTIVE:
        return True
    if member.status in _GONE:
        return False
    if member.status == "restricted":
        return bool(getattr(member, "is_member", False))
    return None


async def run_audit(bot: Bot, user_ids: list[int], *, save: bool = True, sleep=asyncio.sleep) -> AuditResult:
    result = AuditResult(checked_at=datetime.now(timezone.utc).isoformat())
    for user_id in user_ids:
        state = await check_subscription(bot, user_id)
        if state is None:
            result.unknown.add(user_id)
        else:
            result.states[user_id] = state
        await sleep(REQUEST_DELAY_SECONDS)

    if save and result.states and not result.suspicious:
        await db.save_subscription_checks(result.checked_at, result.states)
        result.saved = True
    return result


def _percent(part: int, whole: int) -> str:
    return f"{round(part * 100 / whole)}%" if whole else "-"


def _fmt_time(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d.%m %H:%M") + " UTC"


def build_stats_text(
    total_users: int,
    scenario_rows: list[dict],
    receivers: list[tuple[str, int]],
    result: AuditResult,
    previous_at: str | None,
    previous_states: dict[int, bool],
) -> str:
    by_scenario: dict[str, set[int]] = defaultdict(set)
    for scenario, user_id in receivers:
        by_scenario[scenario].add(user_id)

    lines = [f"👥 Всего пользователей бота: {total_users}", ""]
    if not scenario_rows:
        lines.append("Пока никто не заходил ни в один сценарий.")

    for row in scenario_rows:
        receivers_here = by_scenario.get(row["scenario"], set())
        checked = [uid for uid in receivers_here if uid in result.states]
        subscribed = sum(result.states[uid] for uid in checked)
        line = (
            f"• {row['scenario']}: заходили {row['started']}, получили гайд {row['delivered']}, "
            f"сейчас подписаны на канал {subscribed} ({_percent(subscribed, len(checked))})"
        )
        not_checked = len(receivers_here) - len(checked)
        if not_checked:
            line += f", не удалось проверить {not_checked}"
        lines.append(line)

    all_receivers = {uid for _, uid in receivers}
    all_checked = [uid for uid in all_receivers if uid in result.states]
    all_subscribed = sum(result.states[uid] for uid in all_checked)
    lines.append("")
    lines.append(
        f"Всего получили гайд {len(all_receivers)} чел., сейчас подписаны на канал "
        f"{all_subscribed} ({_percent(all_subscribed, len(all_checked))}). "
        "Один человек считается в каждом сценарии, где получил гайд, тестовые аккаунты не исключены."
    )

    if result.suspicious:
        lines.append("")
        lines.append(
            f"⚠️ Не удалось проверить {len(result.unknown)} из {len(result.states) + len(result.unknown)} человек. "
            "Скорее всего, бот перестал быть администратором канала или Telegram недоступен - "
            "цифры выше неполные и в историю не сохранены."
        )
        return "\n".join(lines)

    if previous_at:
        left = sum(1 for uid, now in result.states.items() if previous_states.get(uid) is True and not now)
        returned = sum(1 for uid, now in result.states.items() if previous_states.get(uid) is False and now)
        lines.append("")
        lines.append(
            f"С прошлой проверки ({_fmt_time(previous_at)}): отписались {left}, вернулись {returned}."
        )
    else:
        lines.append("")
        lines.append("Это первая проверка - динамика (кто отписался) появится при следующем /stats.")
    return "\n".join(lines)
