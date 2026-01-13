# tests/unit/handlers/test_worktree_recovery.py
"""Tests for worktree recovery callbacks."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from codogram.handlers.worktree_recovery import WorktreeRecoveryHandler
from codogram.session_manager import ThreadInfo


@pytest.fixture
def recovery_handler():
    handler = WorktreeRecoveryHandler(
        project_manager=MagicMock(),
        queue=MagicMock(),
        bot=MagicMock(),
    )
    return handler


@pytest.fixture
def mock_callback():
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.message.chat.id = 123
    return callback


class TestWorktreeRecoveryCallbacks:
    @pytest.mark.asyncio
    async def test_wr_recreate_recreates_worktree(self, recovery_handler, mock_callback):
        """wr_recreate callback recreates worktree and starts Claude."""
        mock_callback.data = "wr_recreate:123"
        thread = ThreadInfo(thread_id=123, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        recovery_handler.project_manager.get_thread.return_value = thread
        recovery_handler.project_manager.get_project.return_value = MagicMock(cwd="/repo")

        with patch("codogram.handlers.worktree_recovery.create_worktree") as mock_create:
            mock_create.return_value = (True, "/repo/.worktrees/my-feature")
            with patch.object(recovery_handler, "_start_claude_session", new_callable=AsyncMock):
                await recovery_handler.handle_wr_recreate(mock_callback)

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_create_creates_branch_and_worktree(self, recovery_handler, mock_callback):
        """wr_create callback creates new branch and worktree."""
        mock_callback.data = "wr_create:123"
        thread = ThreadInfo(thread_id=123, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        recovery_handler.project_manager.get_thread.return_value = thread
        recovery_handler.project_manager.get_project.return_value = MagicMock(cwd="/repo")

        with patch("codogram.handlers.worktree_recovery.create_branch_with_worktree") as mock_create:
            mock_create.return_value = (True, "/repo/.worktrees/my-feature")
            with patch.object(recovery_handler, "_start_claude_session", new_callable=AsyncMock):
                await recovery_handler.handle_wr_create(mock_callback)

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_main_archives_topic(self, recovery_handler, mock_callback):
        """wr_main callback archives topic."""
        mock_callback.data = "wr_main:123"
        thread = ThreadInfo(thread_id=123, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        mock_project = MagicMock(cwd="/repo")
        recovery_handler.project_manager.get_thread.return_value = thread
        recovery_handler.project_manager.get_project.return_value = mock_project

        with patch("codogram.handlers.worktree_recovery.archive_thread", new_callable=AsyncMock) as mock_archive:
            await recovery_handler.handle_wr_main(mock_callback)

        mock_archive.assert_called_once_with(
            recovery_handler.bot,
            123,  # chat_id
            mock_project,
            thread,
        )

    @pytest.mark.asyncio
    async def test_wr_cancel_deletes_message(self, recovery_handler, mock_callback):
        """wr_cancel callback just deletes the message."""
        mock_callback.data = "wr_cancel:123"

        await recovery_handler.handle_wr_cancel(mock_callback)

        mock_callback.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_recreate_shows_error_on_failure(self, recovery_handler, mock_callback):
        """wr_recreate shows error message with options on failure."""
        mock_callback.data = "wr_recreate:123"
        thread = ThreadInfo(thread_id=123, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        recovery_handler.project_manager.get_thread.return_value = thread
        recovery_handler.project_manager.get_project.return_value = MagicMock(cwd="/repo")

        with patch("codogram.handlers.worktree_recovery.create_worktree") as mock_create:
            mock_create.return_value = (False, "branch already checked out")
            await recovery_handler.handle_wr_recreate(mock_callback)

        # Should show error with options
        call_args = mock_callback.message.edit_text.call_args
        text = call_args[0][0] if call_args[0] else call_args[1].get("text", "")
        assert "[x]" in text
        assert "/finish" in text
        assert "/thread" in text
        assert "/branch" in text


class TestWorktreeRecoveryEdgeCases:
    @pytest.mark.asyncio
    async def test_wr_recreate_thread_not_found(self, recovery_handler, mock_callback):
        """wr_recreate handles missing thread gracefully."""
        mock_callback.data = "wr_recreate:999"
        recovery_handler.project_manager.get_thread.return_value = None

        await recovery_handler.handle_wr_recreate(mock_callback)

        call_args = mock_callback.message.edit_text.call_args
        text = call_args[0][0] if call_args[0] else call_args[1].get("text", "")
        assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_wr_create_thread_not_found(self, recovery_handler, mock_callback):
        """wr_create handles missing thread gracefully."""
        mock_callback.data = "wr_create:999"
        recovery_handler.project_manager.get_thread.return_value = None

        await recovery_handler.handle_wr_create(mock_callback)

        call_args = mock_callback.message.edit_text.call_args
        text = call_args[0][0] if call_args[0] else call_args[1].get("text", "")
        assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_wr_main_thread_not_found(self, recovery_handler, mock_callback):
        """wr_main handles missing thread gracefully."""
        mock_callback.data = "wr_main:999"
        recovery_handler.project_manager.get_thread.return_value = None

        await recovery_handler.handle_wr_main(mock_callback)

        call_args = mock_callback.message.edit_text.call_args
        text = call_args[0][0] if call_args[0] else call_args[1].get("text", "")
        assert "not found" in text.lower()
