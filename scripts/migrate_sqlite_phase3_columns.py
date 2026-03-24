from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = Path("bot.db")


def ensure_column(cursor: sqlite3.Cursor, table_name: str, column_name: str, ddl: str) -> None:
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    ensure_column(cur, "telegram_users", "created_at", "created_at DATETIME")
    ensure_column(cur, "telegram_users", "updated_at", "updated_at DATETIME")

    cur.execute(
        """
        UPDATE telegram_users
        SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
            updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
        """
    )

    conn.commit()
    conn.close()
    print("sqlite phase3 migration complete")


if __name__ == "__main__":
    main()
