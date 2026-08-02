import os

from dotenv import load_dotenv

load_dotenv()

def _normalize_channel(value: str) -> str:
    value = value.strip()
    if not value or value.startswith("@") or value.startswith("-") or value.isdigit():
        return value
    return f"@{value}"


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MAIN_CHANNEL = _normalize_channel(os.getenv("MAIN_CHANNEL", "@semero4ka_videomaker"))
KLOD_KLUB_URL = os.getenv("KLOD_KLUB_URL", "https://t.me/kuznetsova_klodklub_bot")
DB_PATH = os.getenv("DB_PATH", "bot.db")
