from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    google_sheet_id: str | None
    google_driver_status_sheet_id: str | None
    google_service_account_file: str | None
    google_service_account_json: str | None


def normalize_database_url(raw_url: str) -> str:
    value = raw_url.strip()
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+asyncpg://", 1)
    elif value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+asyncpg://", 1)

    if value.startswith("postgresql+asyncpg://"):
        parts = urlsplit(value)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        sslmode = query.pop("sslmode", None)
        if sslmode and "ssl" not in query:
            query["ssl"] = "require" if sslmode == "require" else sslmode
        value = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    return value


def normalize_sheet_id(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    value = raw_value.strip()
    if not value:
        return None
    if "docs.google.com/spreadsheets/d/" in value:
        parts = value.split("/d/", 1)[1]
        return parts.split("/", 1)[0]
    return value


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        database_url=normalize_database_url(database_url),
        google_sheet_id=normalize_sheet_id(os.getenv("GOOGLE_SHEET_ID")),
        google_driver_status_sheet_id=normalize_sheet_id(os.getenv("GOOGLE_DRIVER_STATUS_SHEET_ID")),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or None,
        google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or None,
    )
