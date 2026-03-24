from __future__ import annotations

import asyncio

from app.services.sheets import SheetsExporter, WIDE_SHEET, wide_columns


async def main() -> None:
    exporter = SheetsExporter()
    client = exporter._build_client()
    if client is None:
        raise RuntimeError("Google Sheets client is not configured")

    await asyncio.to_thread(sync_headers, exporter, client)


def sync_headers(exporter: SheetsExporter, client) -> None:
    book = client.open_by_key(exporter.settings.google_sheet_id)
    headers = wide_columns()
    ws = exporter._get_or_create_ws(book, WIDE_SHEET, headers)

    current_cols = ws.col_count
    if current_cols < len(headers):
        ws.add_cols(len(headers) - current_cols)

    ws.update("A1", [headers], value_input_option="RAW")


if __name__ == "__main__":
    asyncio.run(main())
