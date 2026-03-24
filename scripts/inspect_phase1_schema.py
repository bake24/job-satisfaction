from __future__ import annotations

import asyncio

from sqlalchemy import inspect

from app.db.session import engine


EXPECTED_TABLES = [
    "drivers",
    "dispatchers",
    "driver_dispatchers",
    "telegram_users",
    "survey_runs",
    "survey_responses",
    "survey_exports",
]


async def main() -> None:
    async with engine.begin() as conn:
        def _inspect(sync_conn):
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            print("Tables:")
            for table in tables:
                print(f"- {table}")
            print("")
            missing = [name for name in EXPECTED_TABLES if name not in tables]
            if missing:
                print("Missing expected tables:")
                for name in missing:
                    print(f"- {name}")
            else:
                print("All Phase 1 tables are present.")

        await conn.run_sync(_inspect)


if __name__ == "__main__":
    asyncio.run(main())
