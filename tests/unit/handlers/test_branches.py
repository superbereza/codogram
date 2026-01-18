# tests/unit/handlers/test_branches.py
"""Tests for /branch command - stale worktree handling."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from aiogram.types import Message, Chat

from codogram.session_manager import ThreadInfo
from codogram.domain.worktree_state import WorktreeState


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.chat.title = "Test Project"
    msg.chat.is_forum = True
    msg.message_thread_id = 456
    msg.text = "/branch"
    msg.bot = AsyncMock()
    return msg


@pytest.fixture
def mock_queue():
    queue = AsyncMock()
    queue.enqueue = AsyncMock()
    queue.reply = AsyncMock()
    return queue


class TestBranchStaleWorktree:
    @pytest.mark.asyncio
    async def test_branch_from_stale_worktree_falls_back_to_main(self, mock_message, mock_queue):
        """When current worktree is stale, /branch uses main as base with warning."""
        from codogram.handlers.branches import cmd_branch_create

        thread = ThreadInfo(
            thread_id=456,
            name="old-feature",
            worktree_path="/repo/.worktrees/old-feature"
        )

        mock_project = MagicMock()
        mock_project.cwd = "/repo"
        mock_project.project_name = "test-project"
        mock_project.threads = {456: thread}

        with patch("codogram.handlers.branches.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.handlers.branches.is_git_repo", return_value=True):
                with patch("codogram.handlers.branches.get_worktree_state") as mock_state:
                    mock_state.return_value = WorktreeState.MISSING_WITH_BRANCH
                    with patch("codogram.handlers.branches.get_default_branch", return_value="main"):
                        with patch("codogram.handlers.branches.require_forum_group", new_callable=AsyncMock, return_value=True):
                            with patch("codogram.handlers.branches.require_claude_ready", new_callable=AsyncMock, return_value=True):
                                await cmd_branch_create(mock_message, mock_queue)

        # Verify warning shown and flow continues
        call_args = mock_queue.reply.call_args
        assert call_args is not None, "Expected reply to be called"
        # reply(message, text, ...) - text is second positional arg
        text = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("text", "")
        assert "[!]" in text, f"Expected warning marker [!] in: {text}"
        assert "main" in text.lower(), f"Expected 'main' in message: {text}"

    @pytest.mark.asyncio
    async def test_branch_from_stale_worktree_no_branch_falls_back_to_main(self, mock_message, mock_queue):
        """When worktree AND branch are missing, /branch uses main as base."""
        from codogram.handlers.branches import cmd_branch_create

        thread = ThreadInfo(
            thread_id=456,
            name="deleted-feature",
            worktree_path="/repo/.worktrees/deleted-feature"
        )

        mock_project = MagicMock()
        mock_project.cwd = "/repo"
        mock_project.project_name = "test-project"
        mock_project.threads = {456: thread}

        with patch("codogram.handlers.branches.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.handlers.branches.is_git_repo", return_value=True):
                with patch("codogram.handlers.branches.get_worktree_state") as mock_state:
                    mock_state.return_value = WorktreeState.MISSING_NO_BRANCH
                    with patch("codogram.handlers.branches.get_default_branch", return_value="main"):
                        with patch("codogram.handlers.branches.require_forum_group", new_callable=AsyncMock, return_value=True):
                            with patch("codogram.handlers.branches.require_claude_ready", new_callable=AsyncMock, return_value=True):
                                await cmd_branch_create(mock_message, mock_queue)

        # Verify warning shown
        call_args = mock_queue.reply.call_args
        assert call_args is not None, "Expected reply to be called"
        # reply(message, text, ...) - text is second positional arg
        text = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("text", "")
        assert "[!]" in text, f"Expected warning marker [!] in: {text}"

    @pytest.mark.asyncio
    async def test_branch_from_healthy_worktree_shows_base_selection(self, mock_message, mock_queue):
        """When worktree is OK, /branch shows base branch selection as usual."""
        from codogram.handlers.branches import cmd_branch_create

        thread = ThreadInfo(
            thread_id=456,
            name="feature",
            worktree_path="/repo/.worktrees/feature"
        )

        mock_project = MagicMock()
        mock_project.cwd = "/repo"
        mock_project.project_name = "test-project"
        mock_project.threads = {456: thread}

        with patch("codogram.handlers.branches.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.handlers.branches.is_git_repo", return_value=True):
                with patch("codogram.handlers.branches.get_worktree_state") as mock_state:
                    mock_state.return_value = WorktreeState.OK
                    with patch("codogram.handlers.branches.get_default_branch", return_value="main"):
                        with patch("codogram.handlers.branches.require_forum_group", new_callable=AsyncMock, return_value=True):
                            with patch("codogram.handlers.branches.require_claude_ready", new_callable=AsyncMock, return_value=True):
                                with patch("codogram.handlers.branches.create_flow_service") as mock_service:
                                    mock_service.should_show_prompt.return_value = True
                                    await cmd_branch_create(mock_message, mock_queue)

        # Normal flow - should show name prompt
        call_args = mock_queue.reply.call_args
        assert call_args is not None, "Expected reply to be called"
        # reply(message, text, ...) - text is second positional arg
        text = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("text", "")
        assert "[!]" not in text, f"Expected no warning in healthy worktree: {text}"
        assert "Branch name?" in text, f"Expected name prompt: {text}"
