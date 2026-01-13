# tests/unit/keyboards/test_keyboards.py
import pytest

from codogram.domain.worktree_state import WorktreeState


class TestWorktreeRecoveryKeyboard:
    def test_missing_with_branch_keyboard(self):
        """Keyboard for missing worktree when branch exists."""
        from codogram.keyboards.keyboards import worktree_recovery_keyboard

        kb = worktree_recovery_keyboard(thread_id=123, state=WorktreeState.MISSING_WITH_BRANCH)
        buttons = kb.inline_keyboard

        assert len(buttons) == 3
        assert buttons[0][0].text == "Recreate worktree"
        assert buttons[0][0].callback_data == "wr_recreate:123"
        assert buttons[1][0].text == "Resume in main"
        assert buttons[1][0].callback_data == "wr_main:123"
        assert buttons[2][0].text == "Cancel"
        assert buttons[2][0].callback_data == "wr_cancel:123"

    def test_missing_no_branch_keyboard(self):
        """Keyboard for missing worktree when branch also missing."""
        from codogram.keyboards.keyboards import worktree_recovery_keyboard

        kb = worktree_recovery_keyboard(thread_id=456, state=WorktreeState.MISSING_NO_BRANCH)
        buttons = kb.inline_keyboard

        assert len(buttons) == 3
        assert buttons[0][0].text == "Create new"
        assert buttons[0][0].callback_data == "wr_create:456"
        assert buttons[1][0].text == "Resume in main"
        assert buttons[1][0].callback_data == "wr_main:456"
        assert buttons[2][0].text == "Cancel"
        assert buttons[2][0].callback_data == "wr_cancel:456"
