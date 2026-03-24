from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Base, Dispatcher, Driver, DriverDispatcher
from app.db.schema import bootstrap_schema
from app.db.session import engine, SessionLocal


@dataclass(frozen=True)
class DispatcherSlotInput:
    slot_number: int
    first_name: str
    last_name: str


@dataclass(frozen=True)
class DriverImportRow:
    unit_number: str
    first_name: str
    last_name: str
    is_active: bool
    dispatchers: list[DispatcherSlotInput]


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "y"}


def normalize_name(value: str) -> str:
    return value.strip()


def build_headers(reader: csv.DictReader) -> dict[str, str]:
    return {header.strip().lower(): header for header in (reader.fieldnames or [])}


def parse_row(raw: dict[str, str], headers: dict[str, str]) -> DriverImportRow | None:
    unit_key = headers.get("unit_number") or headers.get("unit")
    first_key = headers.get("first_name")
    last_key = headers.get("last_name")
    active_key = headers.get("is_active")

    if not unit_key or not first_key or not last_key or not active_key:
        raise ValueError(
            "CSV must contain columns: unit_number(or unit), first_name, last_name, is_active"
        )

    unit_number = (raw.get(unit_key) or "").strip()
    first_name = normalize_name(raw.get(first_key) or "")
    last_name = normalize_name(raw.get(last_key) or "")
    if not unit_number or not first_name or not last_name:
        return None

    dispatchers: list[DispatcherSlotInput] = []
    for slot in (1, 2, 3):
        d_first_key = headers.get(f"dispatcher_{slot}_first_name")
        d_last_key = headers.get(f"dispatcher_{slot}_last_name")
        if not d_first_key or not d_last_key:
            continue

        d_first = normalize_name(raw.get(d_first_key) or "")
        d_last = normalize_name(raw.get(d_last_key) or "")
        if not d_first and not d_last:
            continue
        if not d_first or not d_last:
            raise ValueError(
                f"Dispatcher slot {slot} must contain both first and last name for driver "
                f"{unit_number} / {first_name} {last_name}"
            )
        dispatchers.append(
            DispatcherSlotInput(
                slot_number=slot,
                first_name=d_first,
                last_name=d_last,
            )
        )

    return DriverImportRow(
        unit_number=unit_number,
        first_name=first_name,
        last_name=last_name,
        is_active=parse_bool(raw.get(active_key) or "0"),
        dispatchers=dispatchers,
    )


async def get_or_create_driver(session: AsyncSession, row: DriverImportRow) -> Driver:
    result = await session.execute(
        select(Driver).where(
            Driver.unit_number == row.unit_number,
            Driver.first_name == row.first_name,
            Driver.last_name == row.last_name,
        )
    )
    driver = result.scalar_one_or_none()
    if driver:
        driver.is_active = row.is_active
        await session.flush()
        return driver

    driver = Driver(
        unit_number=row.unit_number,
        first_name=row.first_name,
        last_name=row.last_name,
        is_active=row.is_active,
    )
    session.add(driver)
    await session.flush()
    return driver


async def get_or_create_dispatcher(
    session: AsyncSession,
    first_name: str,
    last_name: str,
) -> Dispatcher:
    result = await session.execute(
        select(Dispatcher).where(
            Dispatcher.first_name == first_name,
            Dispatcher.last_name == last_name,
        )
    )
    dispatcher = result.scalar_one_or_none()
    if dispatcher:
        dispatcher.is_active = True
        await session.flush()
        return dispatcher

    dispatcher = Dispatcher(
        first_name=first_name,
        last_name=last_name,
        is_active=True,
    )
    session.add(dispatcher)
    await session.flush()
    return dispatcher


async def replace_driver_dispatchers(
    session: AsyncSession,
    driver: Driver,
    slots: list[DispatcherSlotInput],
) -> None:
    result = await session.execute(
        select(DriverDispatcher).where(DriverDispatcher.driver_id == driver.id)
    )
    existing = {assignment.slot_number: assignment for assignment in result.scalars().all()}
    incoming_slot_numbers = {slot.slot_number for slot in slots}

    for slot in slots:
        dispatcher = await get_or_create_dispatcher(session, slot.first_name, slot.last_name)
        assignment = existing.get(slot.slot_number)
        if assignment:
            assignment.dispatcher_id = dispatcher.id
            assignment.is_active = True
        else:
            session.add(
                DriverDispatcher(
                    driver_id=driver.id,
                    dispatcher_id=dispatcher.id,
                    slot_number=slot.slot_number,
                    is_active=True,
                )
            )

    for slot_number, assignment in existing.items():
        if slot_number not in incoming_slot_numbers:
            await session.delete(assignment)

    await session.flush()


async def import_rows(path: str) -> dict[str, int]:
    async with engine.begin() as conn:
        await bootstrap_schema(conn)

    processed = 0
    created_or_updated_drivers = 0
    assigned_dispatchers = 0

    with open(path, "r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        headers = build_headers(reader)

        async with SessionLocal() as session:
            for raw_row in reader:
                row = parse_row(raw_row, headers)
                if row is None:
                    continue
                processed += 1
                driver = await get_or_create_driver(session, row)
                await replace_driver_dispatchers(session, driver, row.dispatchers)
                created_or_updated_drivers += 1
                assigned_dispatchers += len(row.dispatchers)

            await session.commit()

    return {
        "processed_rows": processed,
        "drivers_upserted": created_or_updated_drivers,
        "dispatcher_slots_assigned": assigned_dispatchers,
    }


async def main(path: str) -> None:
    summary = await import_rows(path)
    for key, value in summary.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to drivers CSV")
    args = parser.parse_args()
    asyncio.run(main(args.file))
