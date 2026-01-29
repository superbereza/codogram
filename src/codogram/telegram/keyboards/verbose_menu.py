# src/codogram/telegram/keyboards/verbose_menu.py
"""Verbose mode menu keyboard."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings


def verbose_menu_keyboard(
    current_mode: str,
    line_limit: int,
    short_id: str,
) -> InlineKeyboardMarkup:
    """Build verbose mode menu keyboard.

    Args:
        current_mode: Current display mode (show_all, lines, headers, current, silence)
        line_limit: Current line limit (for 'lines' mode)
        short_id: Short identifier for callback data

    Returns:
        Inline keyboard with mode selection buttons
    """
    buttons = []

    # Mode buttons
    buttons.append([
        InlineKeyboardButton(
            text="show all" if current_mode != "show_all" else "[show all]",
            callback_data=f"vm:{short_id}:mode:show_all"
        )
    ])

    # Lines mode with +/- controls
    lines_text = f"lines: {line_limit}" if current_mode == "lines" else f"lines ({line_limit})"
    buttons.append([
        InlineKeyboardButton(text="-5", callback_data=f"vm:{short_id}:lines:-5"),
        InlineKeyboardButton(
            text=f"[{lines_text}]" if current_mode == "lines" else lines_text,
            callback_data=f"vm:{short_id}:mode:lines"
        ),
        InlineKeyboardButton(text="+5", callback_data=f"vm:{short_id}:lines:+5"),
    ])

    buttons.append([
        InlineKeyboardButton(
            text="headers only" if current_mode != "headers" else "[headers only]",
            callback_data=f"vm:{short_id}:mode:headers"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="only current" if current_mode != "current" else "[only current]",
            callback_data=f"vm:{short_id}:mode:current"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="total silence" if current_mode != "silence" else "[total silence]",
            callback_data=f"vm:{short_id}:mode:silence"
        )
    ])

    buttons.append([
        InlineKeyboardButton(text=strings.BTN_CLOSE, callback_data=f"vm:{short_id}:close")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def verbose_menu_keyboard_dm(
    current_mode: str,
    line_limit: int,
) -> InlineKeyboardMarkup:
    """Build verbose mode menu keyboard for DM (global defaults).

    Same as verbose_menu_keyboard but with dmvm: prefix for callbacks.

    Args:
        current_mode: Current display mode (show_all, lines, headers, current, silence)
        line_limit: Current line limit (for 'lines' mode)

    Returns:
        Inline keyboard with mode selection buttons
    """
    buttons = []

    # Mode buttons
    buttons.append([
        InlineKeyboardButton(
            text="show all" if current_mode != "show_all" else "[show all]",
            callback_data="dmvm:mode:show_all"
        )
    ])

    # Lines mode with +/- controls
    lines_text = f"lines: {line_limit}" if current_mode == "lines" else f"lines ({line_limit})"
    buttons.append([
        InlineKeyboardButton(text="-5", callback_data="dmvm:lines:-5"),
        InlineKeyboardButton(
            text=f"[{lines_text}]" if current_mode == "lines" else lines_text,
            callback_data="dmvm:mode:lines"
        ),
        InlineKeyboardButton(text="+5", callback_data="dmvm:lines:+5"),
    ])

    buttons.append([
        InlineKeyboardButton(
            text="headers only" if current_mode != "headers" else "[headers only]",
            callback_data="dmvm:mode:headers"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="only current" if current_mode != "current" else "[only current]",
            callback_data="dmvm:mode:current"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="total silence" if current_mode != "silence" else "[total silence]",
            callback_data="dmvm:mode:silence"
        )
    ])

    buttons.append([
        InlineKeyboardButton(text="← Back to settings", callback_data="dmvm:back")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
