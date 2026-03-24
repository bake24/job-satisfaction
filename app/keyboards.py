from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.texts import t


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="English", callback_data="lang:en"),
                InlineKeyboardButton(text="O'zbek", callback_data="lang:uz"),
                InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
            ]
        ]
    )


def yes_no_kb(lang: str, prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("yes", lang), callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text=t("no", lang), callback_data=f"{prefix}:no"),
            ]
        ]
    )


def options_kb(options: list[tuple[str, str]], prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"{prefix}:{code}")] for code, label in options]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def driver_select_kb(drivers: list[tuple[int, str]], lang: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"pickdriver:{driver_id}")] for driver_id, label in drivers]
    rows.append([InlineKeyboardButton(text=t("not_me", lang), callback_data="pickdriver:none")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("menu_start", lang))],
            [
                KeyboardButton(text=t("menu_language", lang)),
                KeyboardButton(text=t("menu_unit", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
