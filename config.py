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

# telegram_id из этого списка не подчиняются правилу "гайд и приглашение шлём один раз" -
# удобно для ручного тестирования сценариев без правки базы
TEST_TELEGRAM_IDS = {
    int(x) for x in os.getenv("TEST_TELEGRAM_IDS", "").split(",") if x.strip()
}

# telegram_id, которым доступны админские команды бота (/stats, /broadcast)
ADMIN_TELEGRAM_IDS = {
    int(x) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()
}
