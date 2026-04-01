from __future__ import annotations

import asyncio

from app.services.sheets import (
    ALL_PROGRESS_SHEET,
    DRIVER_STATUS_SHEET,
    WIDE_SHEET,
    SheetsExporter,
    all_progress_columns,
    driver_status_columns,
    wide_columns,
)


async def main() -> None:
    exporter = SheetsExporter()
    client = exporter._build_client()
    if client is None:
        raise RuntimeError("Google Sheets client is not configured")

    await asyncio.to_thread(sync_headers, exporter, client)


def sync_headers(exporter: SheetsExporter, client) -> None:
    book = client.open_by_key(exporter.settings.google_sheet_id)
    sync_sheet(exporter, book, WIDE_SHEET, wide_columns())
    sync_sheet(exporter, book, ALL_PROGRESS_SHEET, all_progress_columns())
    sync_sheet(exporter, book, DRIVER_STATUS_SHEET, driver_status_columns())


def sync_sheet(exporter: SheetsExporter, book, title: str, headers: list[str]) -> None:
    ws = exporter._get_or_create_ws(book, title, headers)
    current_cols = ws.col_count
    if current_cols < len(headers):
        ws.add_cols(len(headers) - current_cols)

    ws.update("A1", [headers], value_input_option="RAW")


if __name__ == "__main__":
    asyncio.run(main())
