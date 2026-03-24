from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import engine


async def main() -> None:
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info('survey_runs')"))
        columns = {row[1] for row in result.fetchall()}
        if "driver_id" in columns:
            return

        await conn.execute(text("ALTER TABLE survey_runs RENAME TO survey_runs_old"))
        await conn.execute(
            text(
                """
                CREATE TABLE survey_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    driver_id INTEGER NOT NULL,
                    survey_month VARCHAR(7) NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'in_progress',
                    unit_number VARCHAR(32) NOT NULL,
                    first_name VARCHAR(64) NOT NULL,
                    last_name VARCHAR(64) NOT NULL,
                    feedback_type VARCHAR(32),
                    comment TEXT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    CONSTRAINT uq_driver_month UNIQUE (driver_id, survey_month),
                    FOREIGN KEY(telegram_user_id) REFERENCES telegram_users(id),
                    FOREIGN KEY(driver_id) REFERENCES drivers(id)
                )
                """
            )
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_survey_runs_telegram_user_id ON survey_runs (telegram_user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_survey_runs_driver_id ON survey_runs (driver_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_survey_runs_survey_month ON survey_runs (survey_month)"))
        await conn.execute(
            text(
                """
                INSERT OR IGNORE INTO survey_runs (
                    id, telegram_user_id, driver_id, survey_month, status,
                    unit_number, first_name, last_name, feedback_type, comment,
                    started_at, completed_at
                )
                SELECT
                    old.id,
                    old.telegram_user_id,
                    d.id,
                    old.survey_month,
                    old.status,
                    old.unit_number,
                    old.first_name,
                    old.last_name,
                    old.feedback_type,
                    old.comment,
                    old.started_at,
                    old.completed_at
                FROM survey_runs_old old
                JOIN drivers d
                  ON d.unit_number = old.unit_number
                 AND d.first_name = old.first_name
                 AND d.last_name = old.last_name
                """
            )
        )
        await conn.execute(text("DROP TABLE survey_runs_old"))


if __name__ == "__main__":
    asyncio.run(main())
