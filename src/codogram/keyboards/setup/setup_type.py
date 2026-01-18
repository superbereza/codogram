"""Setup type selection keyboards."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings


def setup_type_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for setup type selection (Clone/Connect/New)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_CLONE, callback_data="setup:clone")],
        [InlineKeyboardButton(text=strings.BTN_CONNECT, callback_data="setup:connect")],
        [InlineKeyboardButton(text=strings.BTN_NEW, callback_data="setup:new")],
    ])


def admin_check_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with Check rights button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_CHECK_RIGHTS, callback_data="admin:check")],
    ])
