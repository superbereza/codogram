"""Tests for branch service."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from codogram.services.branch import archive_thread
from codogram.session_manager import ProjectState, ThreadInfo


@pytest.fixture
def mock_project():
    project = MagicMock(spec=ProjectState)
    project.cwd = "/tmp/test-project"
    project.project_name = "test-project"
    return project


@pytest.fixture
def mock_thread():
    thread = MagicMock(spec=ThreadInfo)
    thread.name = "feature-x"
    thread.thread_id = 123
    thread.worktree_path = "/tmp/test-project/.worktrees/feature-x"
    thread.watcher_task = None
    thread.poller_task = None
    thread.binding_task = None
    thread.get_tmux_session = MagicMock(return_value="test-project-feature-x")
    return thread


@pytest.mark.asyncio
async def test_archive_thread_preserves_worktree(mock_project, mock_thread):
    """archive_thread should keep worktree and session_id for resume."""
    bot = AsyncMock()

    with patch("codogram.services.branch.subprocess.run") as mock_run, \
         patch("codogram.services.branch.project_manager") as mock_pm:

        await archive_thread(
            bot=bot,
            chat_id=-100123,
            project=mock_project,
            thread=mock_thread,
        )

        # Should kill tmux
        mock_run.assert_called_once()

        # worktree_path should be preserved (not deleted)
        assert mock_thread.worktree_path == "/tmp/test-project/.worktrees/feature-x"
        assert mock_thread.archived is True
