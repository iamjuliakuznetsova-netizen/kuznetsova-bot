from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    first_seen_at TEXT NOT NULL,
    subscribed_at TEXT
);

CREATE TABLE IF NOT EXISTS scenario_progress (
    telegram_id INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    started_at TEXT NOT NULL,
    guide_sent_at TEXT,
    club_invite_sent_at TEXT,
    PRIMARY KEY (telegram_id, scenario)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def ensure_user(telegram_id: int, username: str | None, first_name: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, first_seen_at, subscribed_at)
            VALUES (?, ?, ?, ?, NULL)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
            """,
            (telegram_id, username, first_name, _now()),
        )
        await db.commit()


async def is_subscribed(telegram_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT subscribed_at FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return row is not None and row[0] is not None


async def mark_subscribed(telegram_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET subscribed_at = ? WHERE telegram_id = ? AND subscribed_at IS NULL",
            (_now(), telegram_id),
        )
        await db.commit()


async def ensure_scenario_progress(telegram_id: int, scenario: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO scenario_progress (telegram_id, scenario, started_at)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id, scenario) DO NOTHING
            """,
            (telegram_id, scenario, _now()),
        )
        await db.commit()


async def get_scenario_progress(telegram_id: int, scenario: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT telegram_id, scenario, started_at, guide_sent_at, club_invite_sent_at
            FROM scenario_progress WHERE telegram_id = ? AND scenario = ?
            """,
            (telegram_id, scenario),
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def mark_guide_sent(telegram_id: int, scenario: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE scenario_progress SET guide_sent_at = ?
            WHERE telegram_id = ? AND scenario = ? AND guide_sent_at IS NULL
            """,
            (_now(), telegram_id, scenario),
        )
        await db.commit()


async def mark_club_invite_sent(telegram_id: int, scenario: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE scenario_progress SET club_invite_sent_at = ?
            WHERE telegram_id = ? AND scenario = ? AND club_invite_sent_at IS NULL
            """,
            (_now(), telegram_id, scenario),
        )
        await db.commit()


async def get_pending_club_invites(cutoff_iso: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT telegram_id, scenario FROM scenario_progress
            WHERE guide_sent_at IS NOT NULL
              AND guide_sent_at <= ?
              AND club_invite_sent_at IS NULL
            """,
            (cutoff_iso,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]
