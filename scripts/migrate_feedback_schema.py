from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import engine


async def main() -> None:
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info('survey_runs')"))
        columns = {row[1] for row in result.fetchall()}
        if "feedback_type" not in columns:
            await conn.execute(text("ALTER TABLE survey_runs ADD COLUMN feedback_type VARCHAR(32)"))


if __name__ == "__main__":
    asyncio.run(main())
