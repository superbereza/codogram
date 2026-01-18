"""Keyboards for /reset_all flow."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import strings


def reset_confirm_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for reset confirmation step."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_CONTINUE, callback_data="reset:continue"),
            InlineKeyboardButton(text=strings.BTN_CANCEL, callback_data="reset:cancel"),
        ],
    ])


def reset_dir_choice_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for directory choice step."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_KEEP_DIR, callback_data="reset:keep"),
            InlineKeyboardButton(text=strings.BTN_DELETE_DIR, callback_data="reset:delete"),
        ],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="reset:back")],
    ])


def reset_uncommitted_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for uncommitted changes warning."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_KEEP_DIR, callback_data="reset:keep"),
            InlineKeyboardButton(text=strings.BTN_DELETE_ANYWAY, callback_data="reset:delete"),
        ],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="reset:back")],
    ])
