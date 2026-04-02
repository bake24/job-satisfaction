from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.db.models import Driver, Response, SurveyRun
from app.handlers.survey import (
    begin_or_lock_run,
    build_all_progress_row,
    build_wide_row,
    catalog,
    export_completed_run_to_sheets,
    resolve_resume_target,
    resume_existing_run,
)
from app.states import SurveyStates
from app.services.sheets import SheetsExporter, all_progress_columns, wide_columns


class FakeWorksheet:
    def __init__(self) -> None:
        self.rows: list[list[str]] = []

    def row_values(self, index: int) -> list[str]:
        if 1 <= index <= len(self.rows):
            return list(self.rows[index - 1])
        return []

    def append_row(self, values: list[str], value_input_option: str = "RAW") -> None:
        self.rows.append(list(values))

    def update(self, cell_range: str, values: list[list[str]], value_input_option: str = "RAW") -> None:
        start = cell_range.split(":")[0]
        row_index = int("".join(ch for ch in start if ch.isdigit()))
        while len(self.rows) < row_index:
            self.rows.append([])
        self.rows[row_index - 1] = list(values[0])

    def col_values(self, col_index: int) -> list[str]:
        result: list[str] = []
        for row in self.rows:
            if len(row) >= col_index:
                result.append(row[col_index - 1])
            else:
                result.append("")
        return result


class FakeBook:
    def __init__(self) -> None:
        self.sheets: dict[str, FakeWorksheet] = {}

    def worksheet(self, title: str) -> FakeWorksheet:
        if title not in self.sheets:
            raise FakeWorksheetNotFound("not found")
        return self.sheets[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        ws = FakeWorksheet()
        self.sheets[title] = ws
        return ws


class FakeClient:
    def __init__(self) -> None:
        self.book = FakeBook()

    def open_by_key(self, key: str) -> FakeBook:
        return self.book


class FakeWorksheetNotFound(Exception):
    pass


def make_run(status: str = "in_progress", completed_at: datetime | None = None) -> SurveyRun:
    run = SurveyRun(
        id=501,
        telegram_user_id=701,
        driver_id=301,
        survey_month="2026-03",
        survey_year=2026,
        survey_quarter=1,
        status=status,
        language="en",
        unit_number="0037",
        first_name="Farukh",
        last_name="Rajabov",
    )
    run.started_at = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
    run.completed_at = completed_at
    return run


def make_response(department: str, question_code: str, answer_code: str, answer_text: str) -> Response:
    return Response(
        survey_run_id=501,
        department=department,
        question_code=question_code,
        answer_code=answer_code,
        answer_text=answer_text,
    )


def make_driver() -> Driver:
    return Driver(id=301, unit_number="0037", first_name="Farukh", last_name="Rajabov", is_active=True)


def responses_for_department(dep_code: str, assigned_dispatchers: list[dict[str, object]] | None = None) -> list[Response]:
    department = next(dep for dep in catalog.departments if dep.code == dep_code)
    responses: list[Response] = []
    if department.requires_contact_gate:
        responses.append(make_response(dep_code, "contact", "yes", "Yes"))
    for question in department.questions:
        responses.append(make_response(dep_code, question.code, "9", "9"))
    if dep_code == "dispatch" and assigned_dispatchers:
        for dispatcher in assigned_dispatchers:
            responses.append(
                make_response(
                    dep_code,
                    f"dispatcher_{dispatcher['slot_number']}_rating",
                    "10",
                    "10",
                )
            )
    return responses


class FakeState:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.state = None

    async def update_data(self, **kwargs: object) -> None:
        self.data.update(kwargs)

    async def set_state(self, value) -> None:
        self.state = value


class FakeMessage:
    def __init__(self) -> None:
        self.answer = AsyncMock()


class ProgressBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = {
            "lang": "en",
            "unit_number": "0037",
            "first_name": "Farukh",
            "last_name": "Rajabov",
            "assigned_dispatchers": [
                {"slot_number": 1, "full_name": "Charlie Ral"},
                {"slot_number": 2, "full_name": "Felix Ral"},
            ],
        }

    def test_build_all_progress_row_partial_answers(self) -> None:
        run = make_run()
        responses = [
            make_response("claims", "contact", "yes", "Yes"),
            make_response("claims", "q1", "9", "9"),
        ]

        row = build_all_progress_row(
            data=self.data,
            run=run,
            responses=responses,
            exported_at_utc="2026-03-30T12:03:00+00:00",
            current_department_code="claims",
            current_question_code="q1",
            progress_step=2,
        )

        self.assertEqual(row["survey_run_id"], "501")
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["claims_contact"], "yes")
        self.assertEqual(row["claims_q1"], "9")
        self.assertEqual(row["current_department"], "claims")
        self.assertEqual(row["current_question_code"], "q1")
        self.assertEqual(row["progress_step"], "2")
        self.assertEqual(row["dispatcher_1_name"], "Charlie Ral")
        self.assertEqual(row["dispatcher_2_name"], "Felix Ral")
        self.assertNotIn("claims_q2", row)

    def test_build_all_progress_row_completed_dispatcher_mapping(self) -> None:
        completed_at = datetime(2026, 3, 30, 12, 30, tzinfo=timezone.utc)
        run = make_run(status="completed", completed_at=completed_at)
        responses = [
            make_response("dispatch", "q1", "8", "8"),
            make_response("dispatch", "dispatcher_1_rating", "10", "10"),
            make_response("management", "feedback", "text", "Strong support"),
        ]

        row = build_all_progress_row(
            data=self.data,
            run=run,
            responses=responses,
            exported_at_utc="2026-03-30T12:31:00+00:00",
            current_department_code="",
            current_question_code="",
            progress_step=3,
        )

        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["completed_at_utc"], completed_at.isoformat())
        self.assertEqual(row["dispatch_q1"], "8")
        self.assertEqual(row["dispatcher_1_rating"], "10")
        self.assertEqual(row["management_feedback"], "Strong support")

    def test_build_wide_row_remains_final_shape(self) -> None:
        run = make_run(status="completed")
        responses = [make_response("hr", "q1", "7", "7")]

        row = build_wide_row(
            data=self.data,
            run=run,
            responses=responses,
            submitted_at_utc="2026-03-30T12:32:00+00:00",
        )

        self.assertNotIn("survey_run_id", row)
        self.assertEqual(row["hr_q1"], "7")
        self.assertEqual(row["dispatcher_1_name"], "Charlie Ral")


class ResumeResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assigned_dispatchers = [
            {"slot_number": 1, "dispatcher_id": 1, "full_name": "Charlie Ral"},
            {"slot_number": 2, "dispatcher_id": 2, "full_name": "Felix Ral"},
        ]

    def test_completed_run_is_blocked(self) -> None:
        target = resolve_resume_target(make_run(status="completed"), [], self.assigned_dispatchers)
        self.assertEqual(target.kind, "already_completed")

    def test_no_answers_resumes_from_first_question(self) -> None:
        target = resolve_resume_target(make_run(), [], self.assigned_dispatchers)
        self.assertEqual(target.kind, "resume_department_question")
        self.assertEqual(target.dep_idx, 0)
        self.assertEqual(target.q_idx, 0)

    def test_claims_contact_no_skips_to_next_department(self) -> None:
        responses: list[Response] = []
        for dep_code in ("hr", "safety", "hos"):
            responses.extend(responses_for_department(dep_code, self.assigned_dispatchers))
        responses.append(make_response("claims", "contact", "no", "No"))

        target = resolve_resume_target(make_run(), responses, self.assigned_dispatchers)

        self.assertEqual(target.kind, "resume_department_question")
        self.assertEqual(catalog.departments[target.dep_idx].code, "fleet")
        self.assertEqual(target.q_idx, 0)

    def test_dispatch_partial_resumes_next_dispatcher_rating(self) -> None:
        responses: list[Response] = []
        for dep_code in ("hr", "safety", "hos", "claims", "fleet"):
            responses.extend(responses_for_department(dep_code, self.assigned_dispatchers))
        responses.extend(
            [
                make_response("dispatch", "q1", "9", "9"),
                make_response("dispatch", "q2", "9", "9"),
                make_response("dispatch", "q3", "9", "9"),
                make_response("dispatch", "q4", "9", "9"),
                make_response("dispatch", "q5", "9", "9"),
                make_response("dispatch", "dispatcher_1_rating", "10", "10"),
            ]
        )

        target = resolve_resume_target(make_run(), responses, self.assigned_dispatchers)

        self.assertEqual(target.kind, "resume_dispatcher_rating")
        self.assertEqual(target.dispatcher_idx, 1)
        self.assertEqual(catalog.departments[target.dep_idx].code, "dispatch")

    def test_ready_to_finish_when_all_required_answers_exist(self) -> None:
        responses: list[Response] = []
        for department in catalog.departments:
            responses.extend(responses_for_department(department.code, self.assigned_dispatchers))

        target = resolve_resume_target(make_run(), responses, self.assigned_dispatchers)

        self.assertEqual(target.kind, "ready_to_finish")

    def test_duplicate_answers_use_latest_persisted_value(self) -> None:
        responses: list[Response] = []
        for dep_code in ("hr", "safety", "hos"):
            responses.extend(responses_for_department(dep_code, self.assigned_dispatchers))
        responses.append(make_response("claims", "contact", "no", "No"))
        responses.append(make_response("claims", "contact", "yes", "Yes"))

        target = resolve_resume_target(make_run(), responses, self.assigned_dispatchers)

        self.assertEqual(target.kind, "resume_department_question")
        self.assertEqual(catalog.departments[target.dep_idx].code, "claims")
        self.assertEqual(target.q_idx, 0)


class SheetsExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_client = FakeClient()
        patcher = patch("app.services.sheets.WorksheetNotFound", FakeWorksheetNotFound)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.exporter = SheetsExporter()
        self.exporter.settings = type(
            "Settings",
            (),
            {
                "google_sheet_id": "sheet-id",
                "google_service_account_json": None,
                "google_service_account_file": None,
            },
        )()

    def test_all_progress_upsert_uses_same_row_for_same_run(self) -> None:
        first = {column: "" for column in all_progress_columns()}
        first.update({"survey_run_id": "501", "status": "in_progress", "claims_q1": "8"})
        second = {column: "" for column in all_progress_columns()}
        second.update({"survey_run_id": "501", "status": "completed", "claims_q1": "9"})

        self.exporter._upsert_all_progress_row_sync(self.fake_client, first)
        self.exporter._upsert_all_progress_row_sync(self.fake_client, second)

        ws = self.fake_client.book.sheets["Survey_All_Progress"]
        self.assertEqual(len(ws.rows), 2)
        self.assertEqual(ws.rows[1][0], "501")
        status_idx = all_progress_columns().index("status")
        claims_q1_idx = all_progress_columns().index("claims_q1")
        self.assertEqual(ws.rows[1][status_idx], "completed")
        self.assertEqual(ws.rows[1][claims_q1_idx], "9")

    def test_upsert_wide_row_updates_same_driver_quarter_row(self) -> None:
        first = {column: "" for column in wide_columns()}
        first.update({"driver_id": "301", "survey_year": "2026", "survey_quarter": "1", "hr_q1": "7"})
        second = {column: "" for column in wide_columns()}
        second.update({"driver_id": "301", "survey_year": "2026", "survey_quarter": "1", "hr_q1": "9"})

        self.exporter._upsert_wide_row_sync(self.fake_client, first)
        self.exporter._upsert_wide_row_sync(self.fake_client, second)

        ws = self.fake_client.book.sheets["Survey_Wide"]
        self.assertEqual(len(ws.rows), 2)
        driver_id_idx = wide_columns().index("driver_id")
        hr_q1_idx = wide_columns().index("hr_q1")
        self.assertEqual(ws.rows[1][driver_id_idx], "301")
        self.assertEqual(ws.rows[1][hr_q1_idx], "9")


class CompletedExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_export_continues_after_progress_failure(self) -> None:
        data = {
            "lang": "en",
            "unit_number": "0037",
            "first_name": "Farukh",
            "last_name": "Rajabov",
            "assigned_dispatchers": [
                {"slot_number": 1, "full_name": "Charlie Ral"},
            ],
        }
        run = make_run(status="completed", completed_at=datetime(2026, 3, 30, 12, 30, tzinfo=timezone.utc))
        responses = [make_response("dispatch", "dispatcher_1_rating", "10", "10")]

        with (
            patch("app.handlers.survey.get_export_record", new=AsyncMock(return_value=None)),
            patch("app.handlers.survey.record_export_success", new=AsyncMock()),
            patch("app.handlers.survey.record_export_failure", new=AsyncMock()),
            patch.object(
                __import__("app.handlers.survey", fromlist=["sheets"]).sheets,
                "upsert_all_progress_row",
                new=AsyncMock(side_effect=RuntimeError("quota")),
            ) as progress_mock,
            patch.object(
                __import__("app.handlers.survey", fromlist=["sheets"]).sheets,
                "upsert_wide_row",
                new=AsyncMock(),
            ) as wide_mock,
            patch.object(
                __import__("app.handlers.survey", fromlist=["sheets"]).sheets,
                "upsert_driver_status_row",
                new=AsyncMock(),
            ) as status_mock,
        ):
            await export_completed_run_to_sheets(
                data=data,
                run=run,
                responses=responses,
                submitted_at_utc="2026-03-30T12:31:00+00:00",
            )

        self.assertEqual(progress_mock.await_count, 1)
        self.assertEqual(wide_mock.await_count, 1)
        self.assertEqual(status_mock.await_count, 1)


class ResumeFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_existing_run_routes_to_next_question(self) -> None:
        message = FakeMessage()
        state = FakeState()
        run = make_run()
        responses = [make_response("hr", "q1", "9", "9")]
        assigned_dispatchers = [{"slot_number": 1, "dispatcher_id": 1, "full_name": "Charlie Ral"}]

        with (
            patch("app.handlers.survey.ask_department_question", new=AsyncMock()) as ask_question,
            patch("app.handlers.survey.ask_department_contact", new=AsyncMock()) as ask_contact,
            patch("app.handlers.survey.ask_dispatcher_rating_question", new=AsyncMock()) as ask_dispatcher,
            patch("app.handlers.survey.finish_survey", new=AsyncMock()) as finish_survey_mock,
        ):
            await resume_existing_run(message, state, "en", run, assigned_dispatchers, responses, 999001)

        self.assertEqual(message.answer.await_count, 1)
        self.assertEqual(ask_question.await_count, 1)
        self.assertEqual(ask_contact.await_count, 0)
        self.assertEqual(ask_dispatcher.await_count, 0)
        self.assertEqual(finish_survey_mock.await_count, 0)
        self.assertEqual(state.data["run_id"], run.id)
        self.assertEqual(state.data["dep_idx"], 0)
        self.assertEqual(state.data["q_idx"], 1)

    async def test_resume_ready_to_finish_completes_run(self) -> None:
        message = FakeMessage()
        state = FakeState()
        run = make_run()
        assigned_dispatchers = [{"slot_number": 1, "dispatcher_id": 1, "full_name": "Charlie Ral"}]
        responses: list[Response] = []
        for department in catalog.departments:
            responses.extend(responses_for_department(department.code, assigned_dispatchers))

        with patch("app.handlers.survey.finish_survey", new=AsyncMock()) as finish_survey_mock:
            await resume_existing_run(message, state, "en", run, assigned_dispatchers, responses, 999001)

        self.assertEqual(finish_survey_mock.await_count, 1)
        self.assertEqual(state.data["run_id"], run.id)

    async def test_begin_or_lock_run_reuses_answered_in_progress_run(self) -> None:
        message = FakeMessage()
        state = FakeState()
        driver = make_driver()
        run = make_run()
        user = SimpleNamespace(id=701, language="en")
        responses = [make_response("hr", "q1", "9", "9")]

        class FakeSession:
            def __init__(self) -> None:
                self.commit = AsyncMock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session_factory = lambda: FakeSession()

        with (
            patch("app.handlers.survey.SessionLocal", new=fake_session_factory),
            patch("app.handlers.survey.get_or_create_user", new=AsyncMock(return_value=user)),
            patch("app.handlers.survey.get_run_for_driver_month", new=AsyncMock(return_value=run)),
            patch(
                "app.handlers.survey.list_active_driver_dispatchers",
                new=AsyncMock(return_value=[(1, 1, "Charlie", "Ral")]),
            ),
            patch("app.handlers.survey.get_responses_for_run", new=AsyncMock(return_value=responses)),
            patch("app.handlers.survey.reset_run", new=AsyncMock()) as reset_run_mock,
            patch("app.handlers.survey.create_run", new=AsyncMock()) as create_run_mock,
            patch("app.handlers.survey.resume_existing_run", new=AsyncMock()) as resume_existing_run_mock,
        ):
            await begin_or_lock_run(message, state, "en", driver, 999001)

        self.assertEqual(reset_run_mock.await_count, 0)
        self.assertEqual(create_run_mock.await_count, 0)
        self.assertEqual(resume_existing_run_mock.await_count, 1)

    async def test_begin_or_lock_run_keeps_completed_block(self) -> None:
        message = FakeMessage()
        state = FakeState()
        driver = make_driver()
        completed_run = make_run(status="completed", completed_at=datetime(2026, 3, 30, 12, 30, tzinfo=timezone.utc))
        user = SimpleNamespace(id=701, language="en")

        class FakeSession:
            def __init__(self) -> None:
                self.commit = AsyncMock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session_factory = lambda: FakeSession()

        with (
            patch("app.handlers.survey.SessionLocal", new=fake_session_factory),
            patch("app.handlers.survey.get_or_create_user", new=AsyncMock(return_value=user)),
            patch("app.handlers.survey.get_run_for_driver_month", new=AsyncMock(return_value=completed_run)),
            patch("app.handlers.survey.list_active_driver_dispatchers", new=AsyncMock(return_value=[])),
        ):
            await begin_or_lock_run(message, state, "en", driver, 999001)

        self.assertEqual(message.answer.await_count, 2)
        self.assertEqual(state.state, SurveyStates.waiting_unit)


if __name__ == "__main__":
    unittest.main()
