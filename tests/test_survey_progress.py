from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.db.models import Response, SurveyRun
from app.handlers.survey import build_all_progress_row, build_wide_row
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

    def test_append_wide_row_remains_append_only(self) -> None:
        first = {column: "" for column in wide_columns()}
        first.update({"driver_id": "301", "hr_q1": "7"})
        second = {column: "" for column in wide_columns()}
        second.update({"driver_id": "301", "hr_q1": "9"})

        self.exporter._append_wide_row_sync(self.fake_client, first)
        self.exporter._append_wide_row_sync(self.fake_client, second)

        ws = self.fake_client.book.sheets["Survey_Wide"]
        self.assertEqual(len(ws.rows), 3)
        driver_id_idx = wide_columns().index("driver_id")
        hr_q1_idx = wide_columns().index("hr_q1")
        self.assertEqual(ws.rows[1][driver_id_idx], "301")
        self.assertEqual(ws.rows[2][driver_id_idx], "301")
        self.assertEqual(ws.rows[1][hr_q1_idx], "7")
        self.assertEqual(ws.rows[2][hr_q1_idx], "9")


if __name__ == "__main__":
    unittest.main()
