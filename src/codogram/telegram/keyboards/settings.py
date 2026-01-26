"""Settings inline keyboard."""

import hashlib
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings


def _short_id(tmux_session: str) -> str:
    """Generate short ID from tmux session name (12 chars max)."""
    return hashlib.md5(tmux_session.encode()).hexdigest()[:12]


# Button groups for pagination
# Each group contains command names (without leading /)
SETTINGS_BUTTON_GROUPS = [
    # Group 0: chat
    ["auto_accept", "response_mode"],
    # Group 1: ui
    ["verbose_mode", "display_bullet", "display_thinking_text"],
    # Group 2: experimental
    ["working_status", "exp_suggestions", "exp_avatar_pack"],
]

# Map command names to callback action codes
_COMMAND_TO_ACTION = {
    "auto_accept": "aa",
    "response_mode": "rm",
    "verbose_mode": "v",
    "display_bullet": "db",
    "display_thinking_text": "dt",
    "working_status": "ws",
    "exp_suggestions": "es",
    "exp_avatar_pack": "ea",
    "shift_tab": "m",
}


def settings_keyboard(tmux_session: str, page: int = 0) -> InlineKeyboardMarkup:
    """Build paginated settings keyboard.

    Args:
        tmux_session: Tmux session name for callback routing
        page: Current page (0-based)

    Returns:
        Inline keyboard with current group buttons + navigation
    """
    sid = _short_id(tmux_session)
    buttons = []

    # Clamp page to valid range
    page = max(0, min(page, len(SETTINGS_BUTTON_GROUPS) - 1))

    # Get current group
    group = SETTINGS_BUTTON_GROUPS[page]
    for cmd in group:
        action = _COMMAND_TO_ACTION.get(cmd, cmd)
        buttons.append([InlineKeyboardButton(
            text=f"/{cmd}",
            callback_data=f"set:{action}:{sid}"
        )])

    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="<",
            callback_data=f"settings:{sid}:page:{page - 1}"
        ))
    if page < len(SETTINGS_BUTTON_GROUPS) - 1:
        nav_row.append(InlineKeyboardButton(
            text=">",
            callback_data=f"settings:{sid}:page:{page + 1}"
        ))
    if nav_row:
        buttons.append(nav_row)

    # Close button
    buttons.append([InlineKeyboardButton(
        text=strings.BTN_CLOSE,
        callback_data="set:close"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
