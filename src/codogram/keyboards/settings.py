"""Settings inline keyboard."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="/auto_accept",
            callback_data=f"settings:auto_accept:{tmux_session}"
        )],
        [InlineKeyboardButton(
            text="/verbose",
            callback_data=f"settings:verbose:{tmux_session}"
        )],
        [InlineKeyboardButton(
            text="/shift_tab",
            callback_data=f"settings:mode:{tmux_session}"
        )],
    ])
