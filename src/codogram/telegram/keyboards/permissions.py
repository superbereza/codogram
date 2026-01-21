"""Inline keyboards for Telegram bot interactions."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings


def permission_keyboard(options: list[str], tmux_session: str) -> InlineKeyboardMarkup:
    """Build inline keyboard from permission options.

    Args:
        options: List of permission options in format ["1. Yes", "2. No", ...]
        tmux_session: Tmux session name for stable routing

    Returns:
        InlineKeyboardMarkup with buttons for each option (max 3) plus Cancel

    Example:
        >>> options = ["1. Yes", "2. Yes, allow all", "3. No"]
        >>> keyboard = permission_keyboard(options, "claude-myproject")
        >>> # Creates buttons: "Yes", "Yes, allow all", "No", "[x] Cancel"
    """
    buttons = []

    for opt in options[:3]:  # Max 3 options
        # Extract number from "1. Yes" -> "1"
        num = opt.split(".")[0].strip()
        label = opt.split(".", 1)[1].strip()[:20]  # Truncate label
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"perm:{num}:{tmux_session}"
        )])

    # Always add Esc button
    buttons.append([InlineKeyboardButton(
        text=strings.BTN_CANCEL_X,
        callback_data=f"perm:esc:{tmux_session}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
