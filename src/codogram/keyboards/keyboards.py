# src/codogram/keyboards/keyboards.py
"""Generic keyboard builders."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from codogram.domain.worktree_state import WorktreeState


def worktree_recovery_keyboard(thread_id: int, state: WorktreeState) -> InlineKeyboardMarkup:
    """Build keyboard for worktree recovery options."""
    builder = InlineKeyboardBuilder()

    if state == WorktreeState.MISSING_WITH_BRANCH:
        builder.button(text="Recreate worktree", callback_data=f"wr_recreate:{thread_id}")
    elif state == WorktreeState.MISSING_NO_BRANCH:
        builder.button(text="Create new", callback_data=f"wr_create:{thread_id}")

    builder.button(text="Resume in main", callback_data=f"wr_main:{thread_id}")
    builder.button(text="Cancel", callback_data=f"wr_cancel:{thread_id}")
    builder.adjust(1)

    return builder.as_markup()
