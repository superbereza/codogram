# tests/unit/domain/test_worktree_state.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from codogram.domain.worktree_state import WorktreeState, get_worktree_state
from codogram.core.session_manager import ThreadInfo


class TestGetWorktreeState:
    def test_no_worktree_returns_ok(self):
        """Thread without worktree_path returns OK."""
        thread = ThreadInfo(thread_id=1, name="test")
        result = get_worktree_state(thread, Path("/repo"))
        assert result == WorktreeState.OK

    def test_valid_worktree_returns_ok(self, tmp_path):
        """Existing worktree path returns OK."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()
        thread = ThreadInfo(thread_id=1, name="test", worktree_path=str(worktree_path))
        result = get_worktree_state(thread, Path("/repo"))
        assert result == WorktreeState.OK

    @patch("codogram.git.utils.branch_exists")
    def test_missing_worktree_with_branch_returns_missing_with_branch(self, mock_branch_exists, tmp_path):
        """Missing worktree but branch exists returns MISSING_WITH_BRANCH."""
        mock_branch_exists.return_value = True
        thread = ThreadInfo(thread_id=1, name="my-feature", worktree_path="/nonexistent")
        result = get_worktree_state(thread, tmp_path)
        assert result == WorktreeState.MISSING_WITH_BRANCH
        mock_branch_exists.assert_called_once_with(tmp_path, "my-feature")

    @patch("codogram.git.utils.branch_exists")
    def test_missing_worktree_no_branch_returns_missing_no_branch(self, mock_branch_exists, tmp_path):
        """Missing worktree and no branch returns MISSING_NO_BRANCH."""
        mock_branch_exists.return_value = False
        thread = ThreadInfo(thread_id=1, name="my-feature", worktree_path="/nonexistent")
        result = get_worktree_state(thread, tmp_path)
        assert result == WorktreeState.MISSING_NO_BRANCH
