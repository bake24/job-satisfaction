from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    google_sheet_id: str | None
    google_service_account_file: str | None
    google_service_account_json: str | None


def normalize_database_url(raw_url: str) -> str:
    value = raw_url.strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        database_url=normalize_database_url(database_url),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID") or None,
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or None,
        google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or None,
    )
