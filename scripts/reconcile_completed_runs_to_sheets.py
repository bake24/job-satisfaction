from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db.models import SurveyRun
from app.db.session import SessionLocal
from app.handlers.survey import export_completed_run_to_sheets, load_run_export_bundle


async def collect_completed_run_ids(run_id: int | None = None) -> list[int]:
    async with SessionLocal() as session:
        stmt = select(SurveyRun.id).where(SurveyRun.status == "completed").order_by(SurveyRun.id)
        if run_id is not None:
            stmt = stmt.where(SurveyRun.id == run_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def reconcile_completed_runs(run_id: int | None = None) -> tuple[int, int]:
    run_ids = await collect_completed_run_ids(run_id)
    processed = 0
    missing = 0

    for current_run_id in run_ids:
        bundle = await load_run_export_bundle(current_run_id)
        if bundle is None:
            missing += 1
            continue

        run, responses, data = bundle
        submitted_at_utc = run.completed_at.isoformat() if run.completed_at else run.started_at.isoformat()
        await export_completed_run_to_sheets(
            data=data,
            run=run,
            responses=responses,
            submitted_at_utc=submitted_at_utc,
        )
        processed += 1

    return processed, missing


async def main(run_id: int | None = None) -> None:
    processed, missing = await reconcile_completed_runs(run_id)
    print(f"processed_runs={processed}")
    print(f"missing_runs={missing}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile completed survey runs from Neon to Google Sheets.")
    parser.add_argument("--run-id", type=int, default=None, help="Optional survey_run_id to reconcile")
    args = parser.parse_args()
    asyncio.run(main(args.run_id))
