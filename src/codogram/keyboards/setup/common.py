"""Common keyboard helpers for setup flow."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings


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
