from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select

from app.db.models import SurveyRun
from app.db.session import SessionLocal
from app.handlers.survey import build_external_driver_status_row, load_run_export_bundle, sheets


def current_year_quarter(now: datetime | None = None) -> tuple[int, int]:
    current = now or datetime.utcnow()
    return current.year, ((current.month - 1) // 3) + 1


async def collect_current_period_run_ids() -> list[int]:
    survey_year, survey_quarter = current_year_quarter()
    async with SessionLocal() as session:
        result = await session.execute(
            select(SurveyRun.id)
            .where(
                SurveyRun.survey_year == survey_year,
                SurveyRun.survey_quarter == survey_quarter,
                SurveyRun.status.in_(("in_progress", "completed")),
            )
            .order_by(SurveyRun.id)
        )
        return list(result.scalars().all())


async def backfill_external_driver_status() -> int:
    processed = 0
    for run_id in await collect_current_period_run_ids():
        bundle = await load_run_export_bundle(run_id)
        if bundle is None:
            continue
        run, _, data = bundle
        await sheets.upsert_external_driver_status_row(build_external_driver_status_row(data, run))
        processed += 1
    return processed


async def main() -> None:
    processed = await backfill_external_driver_status()
    print(f"processed_rows={processed}")


if __name__ == "__main__":
    asyncio.run(main())
