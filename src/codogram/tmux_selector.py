# src/codogram/tmux_selector.py
"""Handle multiple tmux session selection."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def create_tmux_selection_keyboard(tmux_list: list[str], project_name: str) -> InlineKeyboardMarkup:
    """Create inline keyboard for tmux selection."""
    buttons = [
        [InlineKeyboardButton(
            text=f"📟 {tmux}",
            callback_data=f"select_tmux:{project_name}:{tmux}"
        )]
        for tmux in tmux_list
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
