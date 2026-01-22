# tests/unit/handlers/test_worktree_recovery.py
"""Tests for worktree recovery callbacks (now in handlers/start/launch.py)."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from codogram.handlers.start.launch import (
    handle_wr_recreate,
    handle_wr_create,
    handle_wr_main,
    handle_wr_cancel,
)
from codogram.core.session_manager import ThreadInfo


@pytest.fixture
def mock_queue():
    queue = MagicMock()
    queue.edit = AsyncMock()
    queue.send = AsyncMock()
    return queue


@pytest.fixture
def mock_callback():
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.bot = MagicMock()
    callback.bot.reopen_forum_topic = AsyncMock()
    callback.bot.edit_forum_topic = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.message.chat.id = 123
    return callback


class TestWorktreeRecoveryCallbacks:
    @pytest.mark.asyncio
    async def test_wr_recreate_recreates_worktree(self, mock_queue, mock_callback):
        """wr_recreate callback recreates worktree and starts Claude."""
        mock_callback.data = "wr_recreate:456"
        thread = ThreadInfo(thread_id=456, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        mock_project = MagicMock(cwd="/repo", project_name="test")
        mock_project.get_thread.return_value = thread

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.services.branch.create_worktree") as mock_create:
                mock_create.return_value = (True, "/repo/.worktrees/my-feature")
                with patch("codogram.telegram.launch_animation.launch_with_animation", new_callable=AsyncMock):
                    await handle_wr_recreate(mock_callback, mock_queue)

        mock_create.assert_called_once()
        mock_callback.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_create_creates_branch_and_worktree(self, mock_queue, mock_callback):
        """wr_create callback creates new branch and worktree."""
        mock_callback.data = "wr_create:456"
        thread = ThreadInfo(thread_id=456, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        mock_project = MagicMock(cwd="/repo", project_name="test")
        mock_project.get_thread.return_value = thread

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.services.branch.create_branch_with_worktree") as mock_create:
                mock_create.return_value = (True, "/repo/.worktrees/my-feature")
                with patch("codogram.telegram.launch_animation.launch_with_animation", new_callable=AsyncMock):
                    await handle_wr_create(mock_callback, mock_queue)

        mock_create.assert_called_once()
        mock_callback.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_wr_main_archives_topic_and_launches_in_main(self, mock_queue, mock_callback):
        """wr_main callback archives topic and launches Claude in main."""
        mock_callback.data = "wr_main:456"
        thread = ThreadInfo(thread_id=456, name="my-feature", worktree_path="/repo/.worktrees/my-feature")
        main_thread = ThreadInfo(thread_id=None, name="main")
        mock_project = MagicMock(cwd="/repo", project_name="test")
        mock_project.get_thread.return_value = thread
        mock_project.get_or_create_thread.return_value = main_thread

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.services.branch.archive_thread", new_callable=AsyncMock) as mock_archive:
                with patch("codogram.telegram.launch_animation.launch_with_animation", new_callable=AsyncMock):
                    await handle_wr_main(mock_callback, mock_queue)

        mock_archive.assert_called_once_with(
            mock_callback.bot,
            123,  # chat_id
            mock_project,
            thread,
        )

    @pytest.mark.asyncio
    async def test_wr_cancel_deletes_message(self, mock_queue, mock_callback):
        """wr_cancel callback just deletes the message."""
        mock_callback.data = "wr_cancel:456"

        await handle_wr_cancel(mock_callback, mock_queue)

        mock_callback.message.delete.assert_called_once()


class TestWorktreeRecoveryEdgeCases:
    @pytest.mark.asyncio
    async def test_wr_recreate_thread_not_found(self, mock_queue, mock_callback):
        """wr_recreate handles missing thread gracefully."""
        mock_callback.data = "wr_recreate:999"
        mock_project = MagicMock()
        mock_project.get_thread.return_value = None

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            await handle_wr_recreate(mock_callback, mock_queue)

        mock_queue.edit.assert_called()
        call_args = mock_queue.edit.call_args
        text = call_args[0][1] if len(call_args[0]) > 1 else ""
        assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_wr_create_thread_not_found(self, mock_queue, mock_callback):
        """wr_create handles missing thread gracefully."""
        mock_callback.data = "wr_create:999"
        mock_project = MagicMock()
        mock_project.get_thread.return_value = None

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            await handle_wr_create(mock_callback, mock_queue)

        mock_queue.edit.assert_called()
        call_args = mock_queue.edit.call_args
        text = call_args[0][1] if len(call_args[0]) > 1 else ""
        assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_wr_main_thread_not_found(self, mock_queue, mock_callback):
        """wr_main handles missing thread gracefully."""
        mock_callback.data = "wr_main:999"
        mock_project = MagicMock()
        mock_project.get_thread.return_value = None

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            await handle_wr_main(mock_callback, mock_queue)

        mock_queue.edit.assert_called()
        call_args = mock_queue.edit.call_args
        text = call_args[0][1] if len(call_args[0]) > 1 else ""
        assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_wr_recreate_malformed_callback_data(self, mock_queue, mock_callback):
        """wr_recreate handles malformed callback data gracefully."""
        mock_callback.data = "wr_recreate:"  # Missing thread_id

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = MagicMock()
            await handle_wr_recreate(mock_callback, mock_queue)

        mock_queue.edit.assert_called()
        call_args = mock_queue.edit.call_args
        text = call_args[0][1] if len(call_args[0]) > 1 else ""
        assert "invalid" in text.lower()

    @pytest.mark.asyncio
    async def test_wr_create_malformed_callback_data(self, mock_queue, mock_callback):
        """wr_create handles malformed callback data gracefully."""
        mock_callback.data = "wr_create:not_a_number"

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = MagicMock()
            await handle_wr_create(mock_callback, mock_queue)

        mock_queue.edit.assert_called()
        call_args = mock_queue.edit.call_args
        text = call_args[0][1] if len(call_args[0]) > 1 else ""
        assert "invalid" in text.lower()

    @pytest.mark.asyncio
    async def test_wr_main_malformed_callback_data(self, mock_queue, mock_callback):
        """wr_main handles malformed callback data gracefully."""
        mock_callback.data = "wr_main"  # No colon or thread_id

        with patch("codogram.handlers.start.launch.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = MagicMock()
            await handle_wr_main(mock_callback, mock_queue)

        mock_queue.edit.assert_called()
        call_args = mock_queue.edit.call_args
        text = call_args[0][1] if len(call_args[0]) > 1 else ""
        assert "invalid" in text.lower()
