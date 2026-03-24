from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import get_settings
from app.db.schema import bootstrap_schema
from app.db.session import engine
from app.handlers.survey import router as survey_router


async def run() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    logging.basicConfig(level=logging.INFO)

    async with engine.begin() as conn:
        await bootstrap_schema(conn)

    bot = Bot(settings.bot_token)
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Start survey"),
                BotCommand(command="language", description="Change language"),
                BotCommand(command="unit", description="Enter unit number"),
            ]
        )
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(survey_router)

        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
