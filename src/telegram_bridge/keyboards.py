"""Inline keyboards for Telegram bot interactions."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def permission_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    """Build inline keyboard from permission options.

    Args:
        options: List of permission options in format ["1. Yes", "2. No", ...]

    Returns:
        InlineKeyboardMarkup with buttons for each option (max 3) plus Cancel

    Example:
        >>> options = ["1. Yes", "2. Yes, allow all", "3. No"]
        >>> keyboard = permission_keyboard(options)
        >>> # Creates buttons: "Yes", "Yes, allow all", "No", "❌ Cancel"
    """
    buttons = []

    for opt in options[:3]:  # Max 3 options
        # Extract number from "1. Yes" -> "1"
        num = opt.split(".")[0].strip()
        label = opt.split(".", 1)[1].strip()[:20]  # Truncate label
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"perm:{num}"
        )])

    # Always add Esc button
    buttons.append([InlineKeyboardButton(
        text="❌ Cancel",
        callback_data="perm:esc"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
