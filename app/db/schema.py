from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.models import Base


async def bootstrap_schema(conn: AsyncConnection) -> None:
    await conn.run_sync(Base.metadata.create_all)
    dialect = conn.dialect.name
    if dialect == "sqlite":
        await _bootstrap_sqlite(conn)


async def _bootstrap_sqlite(conn: AsyncConnection) -> None:
    def _table_info(sync_conn, table_name: str) -> set[str]:
        rows = sync_conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}

    table_names = set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))

    if "drivers" in table_names:
        driver_columns = await conn.run_sync(lambda sync_conn: _table_info(sync_conn, "drivers"))
        if "language_default" not in driver_columns:
            await conn.execute(text("ALTER TABLE drivers ADD COLUMN language_default VARCHAR(8)"))
        if "created_at" not in driver_columns:
            await conn.execute(text("ALTER TABLE drivers ADD COLUMN created_at DATETIME"))
        if "updated_at" not in driver_columns:
            await conn.execute(text("ALTER TABLE drivers ADD COLUMN updated_at DATETIME"))

    if "survey_runs" in table_names:
        survey_run_columns = await conn.run_sync(lambda sync_conn: _table_info(sync_conn, "survey_runs"))
        if "survey_year" not in survey_run_columns:
            await conn.execute(text("ALTER TABLE survey_runs ADD COLUMN survey_year INTEGER"))
        if "survey_quarter" not in survey_run_columns:
            await conn.execute(text("ALTER TABLE survey_runs ADD COLUMN survey_quarter INTEGER"))
        if "language" not in survey_run_columns:
            await conn.execute(text("ALTER TABLE survey_runs ADD COLUMN language VARCHAR(8)"))
        if "created_at" not in survey_run_columns:
            await conn.execute(text("ALTER TABLE survey_runs ADD COLUMN created_at DATETIME"))
        if "updated_at" not in survey_run_columns:
            await conn.execute(text("ALTER TABLE survey_runs ADD COLUMN updated_at DATETIME"))

        await conn.execute(
            text(
                """
                UPDATE survey_runs
                SET survey_year = COALESCE(
                        survey_year,
                        CASE
                            WHEN length(survey_month) >= 4 THEN CAST(substr(survey_month, 1, 4) AS INTEGER)
                            ELSE CAST(strftime('%Y', 'now') AS INTEGER)
                        END
                    ),
                    survey_quarter = COALESCE(
                        survey_quarter,
                        CASE
                            WHEN length(survey_month) >= 7 THEN ((CAST(substr(survey_month, 6, 2) AS INTEGER) - 1) / 3) + 1
                            ELSE ((CAST(strftime('%m', 'now') AS INTEGER) - 1) / 3) + 1
                        END
                    ),
                    created_at = COALESCE(created_at, started_at),
                    updated_at = COALESCE(updated_at, started_at)
                """
            )
        )

    if "telegram_users" in table_names:
        telegram_user_columns = await conn.run_sync(lambda sync_conn: _table_info(sync_conn, "telegram_users"))
        if "created_at" not in telegram_user_columns:
            await conn.execute(text("ALTER TABLE telegram_users ADD COLUMN created_at DATETIME"))
        if "updated_at" not in telegram_user_columns:
            await conn.execute(text("ALTER TABLE telegram_users ADD COLUMN updated_at DATETIME"))
        await conn.execute(
            text(
                """
                UPDATE telegram_users
                SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
                    updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
                """
            )
        )

    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS dispatchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name VARCHAR(64) NOT NULL,
                last_name VARCHAR(64) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_dispatcher_identity UNIQUE (first_name, last_name)
            )
            """
        )
    )

    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS driver_dispatchers (
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
            CREATE TABLE IF NOT EXISTS survey_exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_run_id INTEGER NOT NULL,
                target VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                last_attempt_at DATETIME,
                error_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_survey_export_target UNIQUE (survey_run_id, target),
                FOREIGN KEY(survey_run_id) REFERENCES survey_runs(id) ON DELETE CASCADE
            )
            """
        )
    )

    if "survey_responses" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE survey_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    survey_run_id INTEGER NOT NULL,
                    department VARCHAR(64) NOT NULL,
                    question_code VARCHAR(64) NOT NULL,
                    answer_code VARCHAR(64) NOT NULL,
                    answer_text TEXT NOT NULL,
                    related_dispatcher_id INTEGER,
                    related_dispatcher_name_snapshot VARCHAR(160),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(survey_run_id) REFERENCES survey_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(related_dispatcher_id) REFERENCES dispatchers(id) ON DELETE SET NULL
                )
                """
            )
        )

        if "responses" in table_names:
            await conn.execute(
                text(
                    """
                    INSERT INTO survey_responses (
                        id,
                        survey_run_id,
                        department,
                        question_code,
                        answer_code,
                        answer_text
                    )
                    SELECT
                        id,
                        survey_run_id,
                        department,
                        question_code,
                        answer_code,
                        answer_text
                    FROM responses
                    """
                )
            )

    await conn.commit()
