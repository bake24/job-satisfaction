from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import engine


async def migrate_postgres() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE driver_dispatchers DROP CONSTRAINT IF EXISTS ck_driver_dispatchers_slot_range"))
        await conn.execute(
            text(
                """
                ALTER TABLE driver_dispatchers
                ADD CONSTRAINT ck_driver_dispatchers_slot_range
                CHECK (slot_number >= 1 AND slot_number <= 4)
                """
            )
        )


async def migrate_sqlite() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text("ALTER TABLE driver_dispatchers RENAME TO driver_dispatchers_old"))
        await conn.execute(
            text(
                """
                CREATE TABLE driver_dispatchers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    driver_id INTEGER NOT NULL,
                    dispatcher_id INTEGER NOT NULL,
                    slot_number INTEGER NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_driver_dispatcher_slot UNIQUE (driver_id, slot_number),
                    CONSTRAINT uq_driver_dispatcher_pair UNIQUE (driver_id, dispatcher_id),
                    CONSTRAINT ck_driver_dispatchers_slot_range CHECK (slot_number >= 1 AND slot_number <= 4),
                    FOREIGN KEY(driver_id) REFERENCES drivers(id) ON DELETE CASCADE,
                    FOREIGN KEY(dispatcher_id) REFERENCES dispatchers(id) ON DELETE CASCADE
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO driver_dispatchers (
                    id, driver_id, dispatcher_id, slot_number, is_active, created_at, updated_at
                )
                SELECT
                    id, driver_id, dispatcher_id, slot_number, is_active, created_at, updated_at
                FROM driver_dispatchers_old
                """
            )
        )
        await conn.execute(text("DROP TABLE driver_dispatchers_old"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))


async def main() -> None:
    dialect = engine.dialect.name
    if dialect == "postgresql":
        await migrate_postgres()
    elif dialect == "sqlite":
        await migrate_sqlite()
    else:
        raise RuntimeError(f"Unsupported database dialect for migration: {dialect}")
    await engine.dispose()
    print("dispatcher_slot_limit=4")


if __name__ == "__main__":
    asyncio.run(main())
