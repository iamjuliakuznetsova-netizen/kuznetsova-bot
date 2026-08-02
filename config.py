import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MAIN_CHANNEL = os.getenv("MAIN_CHANNEL", "@semero4ka_videomaker")
KLOD_KLUB_URL = os.getenv("KLOD_KLUB_URL", "https://t.me/kuznetsova_klodklub_bot")
DB_PATH = os.getenv("DB_PATH", "bot.db")
