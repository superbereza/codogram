"""Common keyboard helpers for setup flow."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .... import strings


def go_back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    """Create keyboard with single Go back button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data=callback_data)],
    ])


def clone_error_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for clone error recovery (per design line 229).

    Buttons: [Retry] [Change URL] [<< Back]
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_RETRY, callback_data="clone:retry"),
            InlineKeyboardButton(text=strings.BTN_CHANGE_URL, callback_data="clone:change_url"),
        ],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="clone:back")],
    ])


def folder_exists_keyboard(context: str) -> InlineKeyboardMarkup:
    """Create keyboard for folder exists scenario (per design line 295).

    Buttons: [Use existing] [Different name] [<< Back]

    Args:
        context: "clone" or "new" - determines back callback
    """
    back_callback = "clone:back" if context == "clone" else "name:back"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_USE_EXISTING, callback_data="exists:use"),
            InlineKeyboardButton(text=strings.BTN_DIFFERENT_NAME, callback_data="exists:rename"),
        ],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data=back_callback)],
    ])
