from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.models import Driver, Response, SurveyRun, TelegramUser
from app.db.repo import (
    add_response,
    complete_run,
    create_run,
    get_driver_by_id,
    get_export_record,
    get_or_create_user,
    get_responses_for_run,
    get_run_for_driver_month,
    get_user_by_telegram_id,
    list_active_driver_dispatchers,
    list_drivers_by_unit,
    mark_export_failure,
    mark_export_success,
    reset_run,
    run_has_responses,
)
from app.db.session import SessionLocal
from app.keyboards import driver_select_kb, language_kb, main_menu_kb, options_kb, yes_no_kb
from app.services.sheets import SheetsExporter
from app.services.survey import Department, SurveyCatalog
from app.states import SurveyStates
from app.texts import t, variants


logger = logging.getLogger(__name__)
router = Router()
catalog = SurveyCatalog(Path(__file__).resolve().parents[1] / "data" / "survey.json")
sheets = SheetsExporter()
ALL_PROGRESS_TARGET = "survey_all_progress"
WIDE_TARGET = "survey_wide"
DRIVER_STATUS_TARGET = "driver_status"


def month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def driver_label(driver: Driver) -> str:
    return f"{driver.first_name} {driver.last_name}".strip()


def current_department(data: dict[str, object]) -> Department:
    return catalog.departments[int(data["dep_idx"])]


def dispatcher_label(dispatcher_data: dict[str, object]) -> str:
    return str(dispatcher_data["full_name"])


async def resolve_lang(state: FSMContext, telegram_id: int) -> str:
    data = await state.get_data()
    state_lang = data.get("lang")
    if isinstance(state_lang, str) and state_lang:
        return state_lang

    async with SessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)
        if user and user.language:
            return user.language
    return "en"


def build_wide_row(
    data: dict[str, object],
    run: SurveyRun,
    responses: list[Response],
    submitted_at_utc: str,
) -> dict[str, str]:
    row: dict[str, str] = {
        "submitted_at_utc": submitted_at_utc,
        "survey_year": str(run.survey_year),
        "survey_quarter": str(run.survey_quarter),
        "survey_period_label": f"{run.survey_year}-Q{run.survey_quarter}",
        "driver_id": str(run.driver_id),
        "telegram_user_id": str(run.telegram_user_id),
        "language": str(data["lang"]),
        "unit_number": str(data["unit_number"]),
        "first_name": str(data["first_name"]),
        "last_name": str(data["last_name"]),
    }
    for dispatcher_data in list(data.get("assigned_dispatchers", [])):
        slot_number = int(dispatcher_data["slot_number"])
        row[f"dispatcher_{slot_number}_name"] = dispatcher_label(dispatcher_data)

    for response in responses:
        if response.department == "dispatch" and response.question_code.startswith("dispatcher_") and response.question_code.endswith("_rating"):
            key = response.question_code
        else:
            key = f"{response.department}_{response.question_code}"
        row[key] = response.answer_text if response.question_code == "feedback" else response.answer_code
    return row


def build_all_progress_row(
    data: dict[str, object],
    run: SurveyRun,
    responses: list[Response],
    exported_at_utc: str,
    current_department_code: str,
    current_question_code: str,
    progress_step: int,
) -> dict[str, str]:
    row: dict[str, str] = {
        "survey_run_id": str(run.id),
        "status": run.status,
        "started_at_utc": run.started_at.isoformat() if run.started_at else "",
        "last_updated_at_utc": exported_at_utc,
        "completed_at_utc": run.completed_at.isoformat() if run.completed_at else "",
        "survey_year": str(run.survey_year),
        "survey_quarter": str(run.survey_quarter),
        "survey_period_label": f"{run.survey_year}-Q{run.survey_quarter}",
        "driver_id": str(run.driver_id),
        "telegram_user_id": str(run.telegram_user_id),
        "language": str(data["lang"]),
        "unit_number": str(data["unit_number"]),
        "first_name": str(data["first_name"]),
        "last_name": str(data["last_name"]),
        "current_department": current_department_code,
        "current_question_code": current_question_code,
        "progress_step": str(progress_step),
    }
    for dispatcher_data in list(data.get("assigned_dispatchers", [])):
        slot_number = int(dispatcher_data["slot_number"])
        row[f"dispatcher_{slot_number}_name"] = dispatcher_label(dispatcher_data)

    for response in responses:
        if response.department == "dispatch" and response.question_code.startswith("dispatcher_") and response.question_code.endswith("_rating"):
            key = response.question_code
        else:
            key = f"{response.department}_{response.question_code}"
        row[key] = response.answer_text if response.question_code == "feedback" else response.answer_code
    return row


def build_driver_status_row(data: dict[str, object], run: SurveyRun) -> dict[str, str]:
    row: dict[str, str] = {
        "driver_id": str(run.driver_id),
        "unit_number": str(data["unit_number"]),
        "first_name": str(data["first_name"]),
        "last_name": str(data["last_name"]),
        "is_active": "1",
        "current_period_submitted": "yes",
        "current_period_submitted_at": run.completed_at.isoformat() if run.completed_at else "",
        "current_period_status": run.status,
    }
    for dispatcher_data in list(data.get("assigned_dispatchers", [])):
        slot_number = int(dispatcher_data["slot_number"])
        row[f"dispatcher_{slot_number}_name"] = dispatcher_label(dispatcher_data)
    return row


async def export_progress_snapshot(
    state: FSMContext,
    run_id: int,
    current_department_code: str,
    current_question_code: str,
) -> None:
    data = await state.get_data()
    async with SessionLocal() as session:
        run = await session.get(SurveyRun, run_id)
        if run is None:
            logger.warning("Skipping Survey_All_Progress export, run %s not found", run_id)
            return
        responses = await get_responses_for_run(session, run_id)

    exported_at_utc = datetime.utcnow().isoformat()
    row = build_all_progress_row(
        data=data,
        run=run,
        responses=responses,
        exported_at_utc=exported_at_utc,
        current_department_code=current_department_code,
        current_question_code=current_question_code,
        progress_step=len(responses),
    )
    try:
        await sheets.upsert_all_progress_row(row)
    except Exception:
        logger.exception(
            "Failed to export Survey_All_Progress for survey_run_id=%s",
            run_id,
        )


async def maybe_send_department_visual(message: Message, department: Department) -> None:
    if department.sticker_file_id:
        try:
            await message.answer_sticker(department.sticker_file_id)
            return
        except Exception:
            logger.exception("Failed to send sticker for department %s", department.code)
    if department.sticker_emoji:
        await message.answer(department.sticker_emoji)


async def load_run_export_bundle(run_id: int) -> tuple[SurveyRun, list[Response], dict[str, object]] | None:
    async with SessionLocal() as session:
        run = await session.get(SurveyRun, run_id)
        if run is None:
            return None
        user = await session.get(TelegramUser, run.telegram_user_id)
        dispatcher_rows = await list_active_driver_dispatchers(session, run.driver_id)
        responses = await get_responses_for_run(session, run_id)

    data: dict[str, object] = {
        "lang": run.language or (user.language if user and user.language else "en"),
        "unit_number": run.unit_number,
        "first_name": run.first_name,
        "last_name": run.last_name,
        "assigned_dispatchers": [
            {
                "slot_number": slot_number,
                "dispatcher_id": dispatcher_id,
                "full_name": f"{first_name} {last_name}".strip(),
            }
            for slot_number, dispatcher_id, first_name, last_name in dispatcher_rows
        ],
    }
    return run, responses, data


async def record_export_success(run_id: int, target: str) -> None:
    async with SessionLocal() as session:
        await mark_export_success(session, run_id, target)
        await session.commit()


async def record_export_failure(run_id: int, target: str, exc: Exception) -> None:
    async with SessionLocal() as session:
        await mark_export_failure(session, run_id, target, str(exc))
        await session.commit()


async def export_sheet_target(run_id: int, target: str, exporter, description: str) -> bool:
    async with SessionLocal() as session:
        export_record = await get_export_record(session, run_id, target)
        if export_record and export_record.status == "completed":
            return True

    try:
        await exporter()
    except Exception as exc:
        logger.exception("Failed to export %s for survey_run_id=%s", description, run_id)
        await record_export_failure(run_id, target, exc)
        return False

    await record_export_success(run_id, target)
    return True


async def export_completed_run_to_sheets(
    data: dict[str, object],
    run: SurveyRun,
    responses: list[Response],
    submitted_at_utc: str,
) -> None:
    progress_row = build_all_progress_row(
        data=data,
        run=run,
        responses=responses,
        exported_at_utc=submitted_at_utc,
        current_department_code="",
        current_question_code="",
        progress_step=len(responses),
    )
    await export_sheet_target(
        run.id,
        ALL_PROGRESS_TARGET,
        lambda: sheets.upsert_all_progress_row(progress_row),
        "Survey_All_Progress",
    )

    wide_row = build_wide_row(
        data=data,
        run=run,
        responses=responses,
        submitted_at_utc=submitted_at_utc,
    )
    await export_sheet_target(
        run.id,
        WIDE_TARGET,
        lambda: sheets.upsert_wide_row(wide_row),
        "Survey_Wide",
    )

    driver_status_row = build_driver_status_row(data=data, run=run)
    await export_sheet_target(
        run.id,
        DRIVER_STATUS_TARGET,
        lambda: sheets.upsert_driver_status_row(driver_status_row),
        "Drivers_Status",
    )


async def ask_department_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = str(data["lang"])
    department = current_department(data)
    progress = f"[{int(data['dep_idx']) + 1}/{len(catalog.departments)}]"
    await maybe_send_department_visual(message, department)
    text = f"{progress} {department.name[lang]}\n\n{department.contact_gate_text[lang]}"
    await message.answer(text, reply_markup=yes_no_kb(lang, "depcontact"))
    await state.set_state(SurveyStates.waiting_department_contact)


async def ask_department_question(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = str(data["lang"])
    department = current_department(data)
    question = department.questions[int(data["q_idx"])]
    options = [(option.code, option.text[lang]) for option in question.options]
    progress = f"[{int(data['dep_idx']) + 1}/{len(catalog.departments)}]"
    if not data.get("scale_notice_shown"):
        await message.answer(t("scale_notice_once", lang))
        await state.update_data(scale_notice_shown=True)
    if int(data["q_idx"]) == 0:
        await maybe_send_department_visual(message, department)
    text = f"{progress} {department.name[lang]}\n\n{question.text[lang]}\n\n{t('rate_1_10', lang)}"
    await message.answer(text, reply_markup=options_kb(options, "qanswer"))
    await state.set_state(SurveyStates.waiting_department_question)


async def ask_department_feedback_decision(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = str(data["lang"])
    await message.answer(t("department_feedback_prompt", lang), reply_markup=yes_no_kb(lang, "depfeedback"))
    await state.set_state(SurveyStates.waiting_department_feedback_decision)


async def ask_dispatcher_rating_question(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = str(data["lang"])
    department = current_department(data)
    dispatchers = list(data.get("assigned_dispatchers", []))
    dispatcher_idx = int(data.get("dispatcher_idx", 0))

    if dispatcher_idx >= len(dispatchers):
        if department.asks_department_feedback:
            await ask_department_feedback_decision(message, state)
        else:
            await move_to_next_department(message, state)
        return

    dispatcher_data = dispatchers[dispatcher_idx]
    progress = f"[{int(data['dep_idx']) + 1}/{len(catalog.departments)}]"
    prompt = t("dispatcher_rating_prompt", lang).format(name=dispatcher_label(dispatcher_data))
    options = [(str(score), str(score)) for score in range(1, 11)]
    text = f"{progress} {department.name[lang]}\n\n{prompt}\n\n{t('rate_1_10', lang)}"
    await message.answer(text, reply_markup=options_kb(options, "drate"))
    await state.set_state(SurveyStates.waiting_dispatcher_rating)


async def move_to_next_department(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    next_idx = int(data["dep_idx"]) + 1
    if next_idx >= len(catalog.departments):
        await finish_survey(message, state)
        return

    await state.update_data(dep_idx=next_idx, q_idx=0)
    next_department = catalog.departments[next_idx]
    if next_department.requires_contact_gate:
        await ask_department_contact(message, state)
    else:
        await ask_department_question(message, state)


async def begin_or_lock_run(message: Message, state: FSMContext, lang: str, driver: Driver, telegram_id: int) -> None:
    m_key = month_key()
    assigned_dispatchers: list[dict[str, object]] = []
    async with SessionLocal() as session:
        user = await get_or_create_user(session, telegram_id, lang)
        existing = await get_run_for_driver_month(session, driver.id, m_key)
        dispatcher_rows = await list_active_driver_dispatchers(session, driver.id)
        assigned_dispatchers = [
            {
                "slot_number": slot_number,
                "dispatcher_id": dispatcher_id,
                "full_name": f"{first_name} {last_name}".strip(),
            }
            for slot_number, dispatcher_id, first_name, last_name in dispatcher_rows
        ]

        if existing and (existing.status == "completed" or await run_has_responses(session, existing.id)):
            await session.commit()
            await message.answer(t("already_completed", lang), reply_markup=main_menu_kb(lang))
            await message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
            await state.set_state(SurveyStates.waiting_unit)
            return

        if existing:
            await reset_run(session, existing, driver.unit_number, driver.first_name, driver.last_name)
            existing.language = lang
            run = existing
        else:
            run = await create_run(
                session=session,
                telegram_user_id=user.id,
                driver_id=driver.id,
                month_key=m_key,
                unit_number=driver.unit_number,
                first_name=driver.first_name,
                last_name=driver.last_name,
                language=lang,
            )
        await session.commit()

    await state.update_data(
        run_id=run.id,
        dep_idx=0,
        q_idx=0,
        dispatcher_idx=0,
        assigned_dispatchers=assigned_dispatchers,
        scale_notice_shown=False,
        lang=lang,
        telegram_id=telegram_id,
        survey_month=m_key,
        unit_number=driver.unit_number,
        first_name=driver.first_name,
        last_name=driver.last_name,
    )

    first_department = catalog.departments[0]
    if first_department.requires_contact_gate:
        await ask_department_contact(message, state)
    else:
        await ask_department_question(message, state)


async def finish_survey(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    run_id = int(data["run_id"])

    async with SessionLocal() as session:
        run = await session.get(SurveyRun, run_id)
        if run is None:
            await message.answer("Run not found.")
            await state.clear()
            return
        await complete_run(session, run)
        responses = await get_responses_for_run(session, run_id)
        await session.commit()

    submitted_at_utc = datetime.utcnow().isoformat()
    await export_completed_run_to_sheets(data=data, run=run, responses=responses, submitted_at_utc=submitted_at_utc)

    await message.answer(t("thanks", str(data["lang"])), reply_markup=main_menu_kb(str(data["lang"])))
    await state.clear()


@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    lang = await resolve_lang(state, message.from_user.id)
    await message.answer("Choose language / Выберите язык / Tilni tanlang", reply_markup=language_kb())
    await message.answer(t("menu_ready", lang), reply_markup=main_menu_kb(lang))
    await state.set_state(SurveyStates.choosing_language)


@router.message(Command("language"))
async def language_cmd(message: Message, state: FSMContext) -> None:
    lang = await resolve_lang(state, message.from_user.id)
    await state.clear()
    await message.answer(t("choose_language", lang), reply_markup=language_kb())
    await message.answer(t("menu_ready", lang), reply_markup=main_menu_kb(lang))
    await state.set_state(SurveyStates.choosing_language)


@router.message(Command("unit"))
async def unit_cmd(message: Message, state: FSMContext) -> None:
    lang = await resolve_lang(state, message.from_user.id)
    await state.clear()
    await state.update_data(lang=lang)
    await message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
    await state.set_state(SurveyStates.waiting_unit)


@router.message(F.text.in_(variants("menu_start")))
async def menu_start_pressed(message: Message, state: FSMContext) -> None:
    lang = await resolve_lang(state, message.from_user.id)
    await state.clear()
    await state.update_data(lang=lang)
    await message.answer(t("welcome", lang), reply_markup=main_menu_kb(lang))
    await message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
    await state.set_state(SurveyStates.waiting_unit)


@router.message(F.text.in_(variants("menu_language")))
async def menu_language_pressed(message: Message, state: FSMContext) -> None:
    await language_cmd(message, state)


@router.message(F.text.in_(variants("menu_unit")))
async def menu_unit_pressed(message: Message, state: FSMContext) -> None:
    await unit_cmd(message, state)


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split(":", 1)[1]
    await state.update_data(lang=lang)
    await callback.message.answer(t("welcome", lang), reply_markup=main_menu_kb(lang))
    await callback.message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
    await state.set_state(SurveyStates.waiting_unit)
    await callback.answer()


@router.message(SurveyStates.waiting_unit)
async def handle_unit(message: Message, state: FSMContext) -> None:
    if not message.text:
        data = await state.get_data()
        await message.answer(t("invalid_input", str(data.get("lang", "en"))))
        return

    data = await state.get_data()
    lang = str(data["lang"])
    unit_number = message.text.strip()

    async with SessionLocal() as session:
        drivers = await list_drivers_by_unit(session, unit_number)

    if not drivers:
        await message.answer(t("driver_not_found", lang), reply_markup=main_menu_kb(lang))
        await message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
        return

    await state.update_data(unit_number=unit_number)

    if len(drivers) == 1:
        driver = drivers[0]
        await state.update_data(candidate_driver_id=driver.id)
        await message.answer(
            f"{t('confirm_driver', lang)}\n\n{driver_label(driver)}",
            reply_markup=yes_no_kb(lang, "driverconfirm"),
        )
        await state.set_state(SurveyStates.waiting_driver_confirm)
        return

    options = [(driver.id, driver_label(driver)) for driver in drivers]
    await message.answer(t("choose_driver", lang), reply_markup=driver_select_kb(options, lang))
    await state.set_state(SurveyStates.waiting_driver_selection)


@router.callback_query(SurveyStates.waiting_driver_confirm, F.data.startswith("driverconfirm:"))
async def handle_driver_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    decision = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = str(data["lang"])

    if decision == "no":
        await callback.message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
        await state.set_state(SurveyStates.waiting_unit)
        await callback.answer()
        return

    candidate_id = data.get("candidate_driver_id")
    if not candidate_id:
        await callback.message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
        await state.set_state(SurveyStates.waiting_unit)
        await callback.answer()
        return

    async with SessionLocal() as session:
        driver = await get_driver_by_id(session, int(candidate_id))

    if not driver:
        await callback.message.answer(t("driver_not_found", lang), reply_markup=main_menu_kb(lang))
        await callback.message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
        await state.set_state(SurveyStates.waiting_unit)
        await callback.answer()
        return

    await begin_or_lock_run(callback.message, state, lang, driver, callback.from_user.id)
    await callback.answer()


@router.callback_query(SurveyStates.waiting_driver_selection, F.data.startswith("pickdriver:"))
async def handle_driver_select(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = str(data["lang"])
    unit_number = str(data.get("unit_number", "")).strip()

    if value == "none":
        await callback.message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
        await state.set_state(SurveyStates.waiting_unit)
        await callback.answer()
        return

    if not value.isdigit():
        await callback.answer()
        return

    async with SessionLocal() as session:
        driver = await get_driver_by_id(session, int(value))

    if not driver or (unit_number and driver.unit_number != unit_number):
        await callback.message.answer(t("driver_not_found", lang), reply_markup=main_menu_kb(lang))
        await callback.message.answer(t("ask_unit", lang), reply_markup=main_menu_kb(lang))
        await state.set_state(SurveyStates.waiting_unit)
        await callback.answer()
        return

    await begin_or_lock_run(callback.message, state, lang, driver, callback.from_user.id)
    await callback.answer()


@router.callback_query(SurveyStates.waiting_department_contact, F.data.startswith("depcontact:"))
async def handle_department_contact(callback: CallbackQuery, state: FSMContext) -> None:
    decision = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = str(data["lang"])
    run_id = int(data["run_id"])
    department = current_department(data)
    answer_text = t("yes", lang) if decision == "yes" else t("no", lang)

    async with SessionLocal() as session:
        await add_response(
            session=session,
            run_id=run_id,
            department=department.code,
            question_code="contact",
            answer_code=decision,
            answer_text=answer_text,
        )
        await session.commit()
    await export_progress_snapshot(
        state=state,
        run_id=run_id,
        current_department_code=department.code,
        current_question_code="contact",
    )

    if decision == "no":
        await move_to_next_department(callback.message, state)
        await callback.answer()
        return

    await state.update_data(q_idx=0)
    await ask_department_question(callback.message, state)
    await callback.answer()


@router.callback_query(SurveyStates.waiting_department_question, F.data.startswith("qanswer:"))
async def handle_department_question(callback: CallbackQuery, state: FSMContext) -> None:
    answer_code = callback.data.split(":", 1)[1]
    data = await state.get_data()
    run_id = int(data["run_id"])
    department = current_department(data)
    question = department.questions[int(data["q_idx"])]
    option = next((candidate for candidate in question.options if candidate.code == answer_code), None)
    if not option:
        await callback.answer()
        return

    async with SessionLocal() as session:
        await add_response(
            session=session,
            run_id=run_id,
            department=department.code,
            question_code=question.code,
            answer_code=option.code,
            answer_text=option.text[str(data["lang"])],
        )
        await session.commit()
    await export_progress_snapshot(
        state=state,
        run_id=run_id,
        current_department_code=department.code,
        current_question_code=question.code,
    )

    next_q_idx = int(data["q_idx"]) + 1
    if next_q_idx < len(department.questions):
        await state.update_data(q_idx=next_q_idx)
        await ask_department_question(callback.message, state)
        await callback.answer()
        return

    if department.code == "dispatch":
        dispatchers = list(data.get("assigned_dispatchers", []))
        if dispatchers:
            await state.update_data(dispatcher_idx=0)
            await ask_dispatcher_rating_question(callback.message, state)
            await callback.answer()
            return

    if department.asks_department_feedback:
        await ask_department_feedback_decision(callback.message, state)
        await callback.answer()
        return

    await move_to_next_department(callback.message, state)
    await callback.answer()


@router.callback_query(SurveyStates.waiting_department_feedback_decision, F.data.startswith("depfeedback:"))
async def handle_department_feedback_decision(callback: CallbackQuery, state: FSMContext) -> None:
    decision = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = str(data["lang"])

    if decision == "yes":
        await callback.message.answer(t("department_feedback_text", lang))
        await state.set_state(SurveyStates.waiting_department_feedback_text)
        await callback.answer()
        return

    await move_to_next_department(callback.message, state)
    await callback.answer()


@router.callback_query(SurveyStates.waiting_dispatcher_rating, F.data.startswith("drate:"))
async def handle_dispatcher_rating(callback: CallbackQuery, state: FSMContext) -> None:
    answer_code = callback.data.split(":", 1)[1]
    data = await state.get_data()
    dispatchers = list(data.get("assigned_dispatchers", []))
    dispatcher_idx = int(data.get("dispatcher_idx", 0))
    if dispatcher_idx >= len(dispatchers):
        await callback.answer()
        return

    dispatcher_data = dispatchers[dispatcher_idx]
    question_code = f"dispatcher_{dispatcher_data['slot_number']}_rating"

    async with SessionLocal() as session:
        await add_response(
            session=session,
            run_id=int(data["run_id"]),
            department="dispatch",
            question_code=question_code,
            answer_code=answer_code,
            answer_text=answer_code,
            related_dispatcher_id=int(dispatcher_data["dispatcher_id"]),
            related_dispatcher_name_snapshot=str(dispatcher_data["full_name"]),
        )
        await session.commit()
    await export_progress_snapshot(
        state=state,
        run_id=int(data["run_id"]),
        current_department_code="dispatch",
        current_question_code=question_code,
    )

    next_dispatcher_idx = dispatcher_idx + 1
    if next_dispatcher_idx < len(dispatchers):
        await state.update_data(dispatcher_idx=next_dispatcher_idx)
        await ask_dispatcher_rating_question(callback.message, state)
        await callback.answer()
        return

    department = current_department(data)
    if department.asks_department_feedback:
        await ask_department_feedback_decision(callback.message, state)
        await callback.answer()
        return

    await move_to_next_department(callback.message, state)
    await callback.answer()


@router.message(SurveyStates.waiting_department_feedback_text)
async def handle_department_feedback_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        data = await state.get_data()
        await message.answer(t("invalid_input", str(data.get("lang", "en"))))
        return

    feedback_text = message.text.strip()
    data = await state.get_data()
    if len(feedback_text) < 5:
        await message.answer(t("comment_too_short", str(data["lang"])))
        return

    department = current_department(data)
    async with SessionLocal() as session:
        await add_response(
            session=session,
            run_id=int(data["run_id"]),
            department=department.code,
            question_code="feedback",
            answer_code="text",
            answer_text=feedback_text,
        )
        await session.commit()
    await export_progress_snapshot(
        state=state,
        run_id=int(data["run_id"]),
        current_department_code=department.code,
        current_question_code="feedback",
    )

    await move_to_next_department(message, state)
