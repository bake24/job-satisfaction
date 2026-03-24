from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import engine


async def main() -> None:
    async with engine.begin() as conn:
        # Skip when already migrated.
        check = await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='drivers'")
        )
        row = check.fetchone()
        if not row or "uq_driver_identity" in (row[0] or ""):
            return

        await conn.execute(text("ALTER TABLE drivers RENAME TO drivers_old"))
        await conn.execute(
            text(
                """
                CREATE TABLE drivers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_number VARCHAR(32) NOT NULL,
                    first_name VARCHAR(64) NOT NULL,
                    last_name VARCHAR(64) NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    CONSTRAINT uq_driver_identity UNIQUE (unit_number, first_name, last_name)
                )
                """
            )
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_drivers_unit_number ON drivers (unit_number)"))
        await conn.execute(
            text(
                """
                INSERT OR IGNORE INTO drivers (unit_number, first_name, last_name, is_active)
                SELECT unit_number, first_name, last_name, is_active
                FROM drivers_old
                """
            )
        )
        await conn.execute(text("DROP TABLE drivers_old"))


if __name__ == "__main__":
    asyncio.run(main())
