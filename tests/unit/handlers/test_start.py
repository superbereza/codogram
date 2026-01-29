"""Tests for /start command - stale worktree handling."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Message, Chat


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.chat.title = "Test Project"
    msg.chat.is_forum = True
    msg.message_thread_id = None
    msg.text = "/start"
    msg.bot = AsyncMock()
    return msg


@pytest.fixture
def mock_queue():
    queue = AsyncMock()
    queue.enqueue = AsyncMock()
    queue.reply = AsyncMock()
    return queue


@pytest.fixture
def mock_state():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    return state


class TestStartStaleWorktree:
    @pytest.mark.asyncio
    async def test_start_with_stale_worktree_and_branch_shows_recovery(self, mock_message, mock_queue, mock_state):
        """Start in topic with stale worktree but branch exists shows recovery options."""
        from codogram.handlers.start import cmd_start
        from codogram.core.session_manager import ThreadInfo
        from codogram.domain.worktree_state import WorktreeState

        mock_message.message_thread_id = 123
        thread = ThreadInfo(
            thread_id=123,
            name="my-feature",
            worktree_path="/nonexistent/path"
        )

        mock_project = MagicMock()
        mock_project.cwd = "/home/user/project"
        mock_project.project_name = "test-project"
        mock_project.threads = {123: thread}
        mock_project.get_thread = MagicMock(return_value=thread)

        with patch("codogram.handlers.start.commands.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.handlers.start.commands.get_worktree_state", return_value=WorktreeState.MISSING_WITH_BRANCH):
                with patch("codogram.handlers.start.commands.worktree_recovery_keyboard") as mock_kb:
                    mock_kb.return_value = MagicMock()
                    await cmd_start(mock_message, mock_state, mock_queue)

        # Should show recovery message with keyboard
        call_args = mock_queue.enqueue.call_args_list
        assert any("[!]" in str(call) for call in call_args), f"Expected [!] in calls: {call_args}"
        mock_kb.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_with_stale_worktree_no_branch_shows_create_new(self, mock_message, mock_queue, mock_state):
        """Start in topic with stale worktree and no branch shows create new option."""
        from codogram.handlers.start import cmd_start
        from codogram.core.session_manager import ThreadInfo
        from codogram.domain.worktree_state import WorktreeState

        mock_message.message_thread_id = 123
        thread = ThreadInfo(
            thread_id=123,
            name="my-feature",
            worktree_path="/nonexistent/path"
        )

        mock_project = MagicMock()
        mock_project.cwd = "/home/user/project"
        mock_project.project_name = "test-project"
        mock_project.threads = {123: thread}
        mock_project.get_thread = MagicMock(return_value=thread)

        with patch("codogram.handlers.start.commands.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.handlers.start.commands.get_worktree_state", return_value=WorktreeState.MISSING_NO_BRANCH):
                with patch("codogram.handlers.start.commands.worktree_recovery_keyboard") as mock_kb:
                    mock_kb.return_value = MagicMock()
                    await cmd_start(mock_message, mock_state, mock_queue)

        mock_kb.assert_called_once_with(123, WorktreeState.MISSING_NO_BRANCH)
