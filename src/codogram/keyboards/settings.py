"""Settings inline keyboard."""

import hashlib
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import strings


def _short_id(tmux_session: str) -> str:
    """Generate short ID from tmux session name (12 chars max)."""
    return hashlib.md5(tmux_session.encode()).hexdigest()[:12]


def settings_keyboard(tmux_session: str) -> InlineKeyboardMarkup:
    """Build settings keyboard with toggle buttons.

    Args:
        tmux_session: Tmux session name for callback routing

    Returns:
        InlineKeyboardMarkup with vertical buttons:
        - /auto_accept
        - /verbose
        - /shift_tab
    """
    sid = _short_id(tmux_session)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="/auto_accept",
            callback_data=f"set:aa:{sid}"
        )],
        [InlineKeyboardButton(
            text="/verbose",
            callback_data=f"set:v:{sid}"
        )],
        [InlineKeyboardButton(
            text="/shift_tab",
            callback_data=f"set:m:{sid}"
        )],
        [InlineKeyboardButton(
            text=strings.BTN_CLOSE,
            callback_data="set:close"
        )],
    ])
