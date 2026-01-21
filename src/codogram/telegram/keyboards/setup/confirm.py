# src/codogram/keyboards/setup/confirm.py
"""Confirmation keyboards for setup flow."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .... import strings


def rename_confirm_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for rename confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_RENAME_YES, callback_data="rename:yes"),
            InlineKeyboardButton(text=strings.BTN_RENAME_NO, callback_data="rename:no"),
        ],
        [
            InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="rename:back"),
        ],
    ])
