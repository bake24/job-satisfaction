from __future__ import annotations

import asyncio
import json
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from gspread import WorksheetNotFound

from app.config import get_settings


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

WIDE_SHEET = "Survey_Wide"
DRIVER_STATUS_SHEET = "Drivers_Status"
ALL_PROGRESS_SHEET = "Survey_All_Progress"


def wide_columns() -> list[str]:
    return [
        "submitted_at_utc",
        "survey_year",
        "survey_quarter",
        "survey_period_label",
        "driver_id",
        "telegram_user_id",
        "language",
        "unit_number",
        "first_name",
        "last_name",
        "hr_q1",
        "hr_q2",
        "hr_q3",
        "hr_q4",
        "hr_q5",
        "hr_feedback",
        "safety_q1",
        "safety_q2",
        "safety_q3",
        "safety_q4",
        "safety_q5",
        "safety_feedback",
        "hos_q1",
        "hos_q2",
        "hos_q3",
        "hos_q4",
        "hos_q5",
        "hos_feedback",
        "claims_contact",
        "claims_q1",
        "claims_q2",
        "claims_q3",
        "claims_q4",
        "claims_q5",
        "claims_feedback",
        "fleet_q1",
        "fleet_q2",
        "fleet_q3",
        "fleet_q4",
        "fleet_q5",
        "fleet_feedback",
        "dispatch_q1",
        "dispatch_q2",
        "dispatch_q3",
        "dispatch_q4",
        "dispatch_q5",
        "dispatcher_1_name",
        "dispatcher_2_name",
        "dispatcher_3_name",
        "dispatcher_4_name",
        "dispatcher_1_rating",
        "dispatcher_2_rating",
        "dispatcher_3_rating",
        "dispatcher_4_rating",
        "dispatch_feedback",
        "accounting_q1",
        "accounting_q2",
        "accounting_q3",
        "accounting_q4",
        "accounting_q5",
        "accounting_feedback",
        "management_q1",
        "management_q2",
        "management_q3",
        "management_q4",
        "management_q5",
        "management_feedback",
    ]


def all_progress_columns() -> list[str]:
    return [
        "survey_run_id",
        "status",
        "started_at_utc",
        "last_updated_at_utc",
        "completed_at_utc",
        "survey_year",
        "survey_quarter",
        "survey_period_label",
        "driver_id",
        "telegram_user_id",
        "language",
        "unit_number",
        "first_name",
        "last_name",
        "current_department",
        "current_question_code",
        "progress_step",
        "dispatcher_1_name",
        "dispatcher_2_name",
        "dispatcher_3_name",
        "dispatcher_4_name",
        "hr_q1",
        "hr_q2",
        "hr_q3",
        "hr_q4",
        "hr_q5",
        "hr_feedback",
        "safety_q1",
        "safety_q2",
        "safety_q3",
        "safety_q4",
        "safety_q5",
        "safety_feedback",
        "hos_q1",
        "hos_q2",
        "hos_q3",
        "hos_q4",
        "hos_q5",
        "hos_feedback",
        "claims_contact",
        "claims_q1",
        "claims_q2",
        "claims_q3",
        "claims_q4",
        "claims_q5",
        "claims_feedback",
        "fleet_q1",
        "fleet_q2",
        "fleet_q3",
        "fleet_q4",
        "fleet_q5",
        "fleet_feedback",
        "dispatch_q1",
        "dispatch_q2",
        "dispatch_q3",
        "dispatch_q4",
        "dispatch_q5",
        "dispatcher_1_rating",
        "dispatcher_2_rating",
        "dispatcher_3_rating",
        "dispatcher_4_rating",
        "dispatch_feedback",
        "accounting_q1",
        "accounting_q2",
        "accounting_q3",
        "accounting_q4",
        "accounting_q5",
        "accounting_feedback",
        "management_q1",
        "management_q2",
        "management_q3",
        "management_q4",
        "management_q5",
        "management_feedback",
    ]


def driver_status_columns() -> list[str]:
    return [
        "driver_id",
        "unit_number",
        "first_name",
        "last_name",
        "is_active",
        "dispatcher_1_name",
        "dispatcher_2_name",
        "dispatcher_3_name",
        "dispatcher_4_name",
        "current_period_submitted",
        "current_period_submitted_at",
        "current_period_status",
    ]


class SheetsExporter:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_client(self) -> gspread.Client | None:
        if not self.settings.google_sheet_id:
            return None
        if self.settings.google_service_account_json:
            payload = json.loads(self.settings.google_service_account_json)
            creds = Credentials.from_service_account_info(payload, scopes=SCOPES)
            return gspread.authorize(creds)
        if self.settings.google_service_account_file:
            creds = Credentials.from_service_account_file(self.settings.google_service_account_file, scopes=SCOPES)
            return gspread.authorize(creds)
        return None

    async def append_wide_row(self, row_data: dict[str, Any]) -> None:
        client = self._build_client()
        if not client:
            return
        await asyncio.to_thread(self._append_wide_row_sync, client, row_data)

    async def upsert_all_progress_row(self, row_data: dict[str, Any]) -> None:
        client = self._build_client()
        if not client:
            return
        await asyncio.to_thread(self._upsert_all_progress_row_sync, client, row_data)

    async def upsert_driver_status_row(self, row_data: dict[str, Any]) -> None:
        client = self._build_client()
        if not client:
            return
        await asyncio.to_thread(self._upsert_driver_status_row_sync, client, row_data)

    def _append_wide_row_sync(self, client: gspread.Client, row_data: dict[str, Any]) -> None:
        book = client.open_by_key(self.settings.google_sheet_id)
        ws = self._get_or_create_ws(book, WIDE_SHEET, wide_columns())
        self._ensure_headers(ws, wide_columns())
        headers = ws.row_values(1)
        row_values = [str(row_data.get(column, "")) for column in headers]
        ws.append_row(row_values, value_input_option="RAW")

    def _upsert_all_progress_row_sync(self, client: gspread.Client, row_data: dict[str, Any]) -> None:
        book = client.open_by_key(self.settings.google_sheet_id)
        ws = self._get_or_create_ws(book, ALL_PROGRESS_SHEET, all_progress_columns())
        self._ensure_headers(ws, all_progress_columns())
        headers = ws.row_values(1)
        survey_run_id = str(row_data.get("survey_run_id", ""))
        existing_row_idx = self._find_row_by_first_column(ws, survey_run_id)
        row_values = [str(row_data.get(column, "")) for column in headers]
        if existing_row_idx is None:
            ws.append_row(row_values, value_input_option="RAW")
        else:
            cell_range = f"A{existing_row_idx}:{self._column_letter(len(headers))}{existing_row_idx}"
            ws.update(cell_range, [row_values], value_input_option="RAW")

    def _upsert_driver_status_row_sync(self, client: gspread.Client, row_data: dict[str, Any]) -> None:
        book = client.open_by_key(self.settings.google_sheet_id)
        ws = self._get_or_create_ws(book, DRIVER_STATUS_SHEET, driver_status_columns())
        self._ensure_headers(ws, driver_status_columns())
        headers = ws.row_values(1)
        driver_id = str(row_data.get("driver_id", ""))
        existing_row_idx = self._find_row_by_first_column(ws, driver_id)
        row_values = [str(row_data.get(column, "")) for column in headers]
        if existing_row_idx is None:
            ws.append_row(row_values, value_input_option="RAW")
        else:
            cell_range = f"A{existing_row_idx}:{self._column_letter(len(headers))}{existing_row_idx}"
            ws.update(cell_range, [row_values], value_input_option="RAW")

    def _get_or_create_ws(self, book: gspread.Spreadsheet, title: str, headers: list[str]) -> gspread.Worksheet:
        try:
            ws = book.worksheet(title)
            if not ws.row_values(1):
                ws.append_row(headers)
            return ws
        except WorksheetNotFound:
            ws = book.add_worksheet(title=title, rows=2000, cols=max(64, len(headers) + 4))
            ws.append_row(headers)
            return ws

    def _ensure_headers(self, ws: gspread.Worksheet, headers: list[str]) -> None:
        current = ws.row_values(1)
        if current != headers:
            ws.update(f"A1:{self._column_letter(len(headers))}1", [headers], value_input_option="RAW")

    def _find_row_by_first_column(self, ws: gspread.Worksheet, first_value: str) -> int | None:
        if not first_value:
            return None
        col_values = ws.col_values(1)
        for idx, value in enumerate(col_values[1:], start=2):
            if value == first_value:
                return idx
        return None

    def _column_letter(self, index: int) -> str:
        result = []
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            result.append(chr(65 + remainder))
        return "".join(reversed(result))
