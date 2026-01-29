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
    total_pages = len(SETTINGS_BUTTON_GROUPS)

    # Navigation row at top: [◀] [1/3] [▶]
    if total_pages > 1:
        nav_row = []
        # Left button
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀",
                callback_data=f"settings:{sid}:page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text="•",
                callback_data="settings:noop"
            ))
        # Page indicator
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="settings:noop"
        ))
        # Right button
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶",
                callback_data=f"settings:{sid}:page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text="•",
                callback_data="settings:noop"
            ))
        buttons.append(nav_row)

    # Get current group
    group = SETTINGS_BUTTON_GROUPS[page]
    for cmd in group:
        action = _COMMAND_TO_ACTION.get(cmd, cmd)
        buttons.append([InlineKeyboardButton(
            text=f"/{cmd}",
            callback_data=f"set:{action}:{sid}"
        )])

    # Close button at bottom
    buttons.append([InlineKeyboardButton(
        text=strings.BTN_CLOSE,
        callback_data="set:close"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Button groups for DM (same as regular, no claude section to exclude)
SETTINGS_BUTTON_GROUPS_DM = [
    # Group 0: chat
    ["auto_accept", "response_mode"],
    # Group 1: ui
    ["verbose_mode", "display_bullet", "display_thinking_text"],
    # Group 2: experimental
    ["working_status", "exp_suggestions", "exp_avatar_pack"],
]


def settings_keyboard_dm(page: int = 0) -> InlineKeyboardMarkup:
    """Build paginated settings keyboard for DM (global defaults).

    Args:
        page: Current page (0-based)

    Returns:
        Inline keyboard with current group buttons + navigation
    """
    buttons = []

    # Clamp page to valid range
    page = max(0, min(page, len(SETTINGS_BUTTON_GROUPS_DM) - 1))

    # Get current group
    group = SETTINGS_BUTTON_GROUPS_DM[page]
    for cmd in group:
        action = _COMMAND_TO_ACTION.get(cmd, cmd)
        buttons.append([InlineKeyboardButton(
            text=f"/{cmd}",
            callback_data=f"dmset:{action}"
        )])

    # Navigation + Close row
    total_pages = len(SETTINGS_BUTTON_GROUPS_DM)
    nav_close_row = []

    if total_pages > 1 and page > 0:
        nav_close_row.append(InlineKeyboardButton(
            text="◀",
            callback_data=f"dmset:page:{page - 1}"
        ))
    elif total_pages > 1:
        nav_close_row.append(InlineKeyboardButton(
            text="•",
            callback_data="dmset:noop"
        ))

    nav_close_row.append(InlineKeyboardButton(
        text=strings.BTN_CLOSE,
        callback_data="dmset:close"
    ))

    if total_pages > 1 and page < total_pages - 1:
        nav_close_row.append(InlineKeyboardButton(
            text="▶",
            callback_data=f"dmset:page:{page + 1}"
        ))
    elif total_pages > 1:
        nav_close_row.append(InlineKeyboardButton(
            text="•",
            callback_data="dmset:noop"
        ))

    buttons.append(nav_close_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)
