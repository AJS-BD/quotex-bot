# config.py
import os
from dotenv import load_dotenv

load_dotenv()

def get_env(key: str) -> str:
    """Get required environment variable, raise if missing."""
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"Missing required env var: {key}")
    return value

DATABASE_URL = get_env("DATABASE_URL")
# Railway provides postgresql:// but SQLAlchemy async needs postgresql+asyncpg://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = get_env("ADMIN_CHAT_ID")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENCRYPTION_KEY = get_env("ENCRYPTION_KEY")
