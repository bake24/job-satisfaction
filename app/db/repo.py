from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Dispatcher, Driver, DriverDispatcher, Response, SurveyExport, SurveyRun, TelegramUser


async def get_or_create_user(session: AsyncSession, telegram_id: int, language: str) -> TelegramUser:
    result = await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.language = language
        await session.flush()
        return user

    user = TelegramUser(telegram_id=telegram_id, language=language)
    session.add(user)
    await session.flush()
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> TelegramUser | None:
    result = await session.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def find_driver(session: AsyncSession, unit_number: str, first_name: str, last_name: str) -> Driver | None:
    result = await session.execute(
        select(Driver).where(
            Driver.unit_number == unit_number.strip(),
            Driver.first_name.ilike(first_name.strip()),
            Driver.last_name.ilike(last_name.strip()),
            Driver.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def list_drivers_by_unit(session: AsyncSession, unit_number: str) -> list[Driver]:
    result = await session.execute(
        select(Driver).where(Driver.unit_number == unit_number.strip(), Driver.is_active.is_(True)).order_by(Driver.last_name, Driver.first_name)
    )
    return list(result.scalars().all())


async def get_driver_by_id(session: AsyncSession, driver_id: int) -> Driver | None:
    result = await session.execute(select(Driver).where(Driver.id == driver_id, Driver.is_active.is_(True)))
    return result.scalar_one_or_none()


async def get_run_for_driver_month(session: AsyncSession, driver_id: int, month_key: str) -> SurveyRun | None:
    result = await session.execute(
        select(SurveyRun).where(
            SurveyRun.driver_id == driver_id,
            SurveyRun.survey_month == month_key,
        )
    )
    return result.scalar_one_or_none()


async def create_run(
    session: AsyncSession,
    telegram_user_id: int,
    driver_id: int,
    month_key: str,
    unit_number: str,
    first_name: str,
    last_name: str,
    language: str | None = None,
) -> SurveyRun:
    run = SurveyRun(
        telegram_user_id=telegram_user_id,
        driver_id=driver_id,
        survey_month=month_key,
        unit_number=unit_number.strip(),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        status="in_progress",
        language=language,
    )
    session.add(run)
    await session.flush()
    return run


async def add_response(
    session: AsyncSession,
    run_id: int,
    department: str,
    question_code: str,
    answer_code: str,
    answer_text: str,
    related_dispatcher_id: int | None = None,
    related_dispatcher_name_snapshot: str | None = None,
) -> None:
    session.add(
        Response(
            survey_run_id=run_id,
            department=department,
            question_code=question_code,
            answer_code=answer_code,
            answer_text=answer_text,
            related_dispatcher_id=related_dispatcher_id,
            related_dispatcher_name_snapshot=related_dispatcher_name_snapshot,
        )
    )
    await session.flush()


async def list_active_driver_dispatchers(session: AsyncSession, driver_id: int) -> list[tuple[int, int, str, str]]:
    result = await session.execute(
        select(
            DriverDispatcher.slot_number,
            Dispatcher.id,
            Dispatcher.first_name,
            Dispatcher.last_name,
        )
        .join(Dispatcher, Dispatcher.id == DriverDispatcher.dispatcher_id)
        .where(
            DriverDispatcher.driver_id == driver_id,
            DriverDispatcher.is_active.is_(True),
            Dispatcher.is_active.is_(True),
        )
        .order_by(DriverDispatcher.slot_number)
    )
    return list(result.all())


async def complete_run(session: AsyncSession, run: SurveyRun) -> None:
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    await session.flush()


async def get_responses_for_run(session: AsyncSession, run_id: int) -> list[Response]:
    result = await session.execute(select(Response).where(Response.survey_run_id == run_id))
    return list(result.scalars().all())


async def run_has_responses(session: AsyncSession, run_id: int) -> bool:
    result = await session.execute(select(Response.id).where(Response.survey_run_id == run_id).limit(1))
    return result.scalar_one_or_none() is not None


async def reset_run(session: AsyncSession, run: SurveyRun, unit_number: str, first_name: str, last_name: str) -> None:
    run.status = "in_progress"
    run.comment = None
    run.completed_at = None
    run.unit_number = unit_number
    run.first_name = first_name
    run.last_name = last_name
    result = await session.execute(select(Response).where(Response.survey_run_id == run.id))
    for resp in result.scalars().all():
        await session.delete(resp)
    await session.flush()


async def get_export_record(session: AsyncSession, run_id: int, target: str) -> SurveyExport | None:
    result = await session.execute(
        select(SurveyExport).where(
            SurveyExport.survey_run_id == run_id,
            SurveyExport.target == target,
        )
    )
    return result.scalar_one_or_none()


async def get_or_create_export_record(session: AsyncSession, run_id: int, target: str) -> SurveyExport:
    existing = await get_export_record(session, run_id, target)
    if existing:
        return existing

    export = SurveyExport(survey_run_id=run_id, target=target)
    session.add(export)
    await session.flush()
    return export


async def mark_export_success(session: AsyncSession, run_id: int, target: str) -> None:
    export = await get_or_create_export_record(session, run_id, target)
    export.status = "completed"
    export.last_attempt_at = datetime.now(timezone.utc)
    export.error_message = None
    await session.flush()


async def mark_export_failure(session: AsyncSession, run_id: int, target: str, error_message: str) -> None:
    export = await get_or_create_export_record(session, run_id, target)
    export.status = "failed"
    export.last_attempt_at = datetime.now(timezone.utc)
    export.error_message = error_message[:2000]
    await session.flush()

