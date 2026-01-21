"""Inline keyboard for AskUserQuestion prompts."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings


def ask_user_keyboard(options: list[str], tmux_session: str) -> InlineKeyboardMarkup:
    """Build inline keyboard from AskUserQuestion options.

    Args:
        options: List of options in format ["1. Option", "2. Option", ...]
        tmux_session: Tmux session name for stable routing

    Returns:
        InlineKeyboardMarkup with buttons for each option plus Cancel
    """
    buttons = []

    for opt in options[:4]:  # Max 4 options
        # Extract number from "1. Option" -> "1"
        num = opt.split(".")[0].strip()
        label = opt.split(".", 1)[1].strip()[:20]  # Truncate label

        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"ask:{num}:{tmux_session}"
        )])

    # Always add Esc button
    buttons.append([InlineKeyboardButton(
        text=strings.BTN_CANCEL_X,
        callback_data=f"ask:esc:{tmux_session}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
