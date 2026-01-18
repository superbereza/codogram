"""Tests for /finish command - stale worktree handling."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Message, Chat


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.message_thread_id = 456
    msg.text = "/finish"
    return msg


@pytest.fixture
def mock_queue():
    return AsyncMock()


class TestFinishStaleWorktree:
    @pytest.mark.asyncio
    async def test_finish_with_stale_worktree_shows_warning(self, mock_message, mock_queue):
        """Finish with stale worktree shows warning and archives."""
        from codogram.handlers.finish import cmd_finish
        from codogram.session_manager import ThreadInfo

        thread = ThreadInfo(
            thread_id=456,
            name="my-feature",
            worktree_path="/nonexistent/path"
        )

        mock_project = MagicMock()
        mock_project.cwd = "/home/user/project"
        mock_project.get_thread = MagicMock(return_value=thread)

        with patch("codogram.handlers.finish.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = mock_project
            with patch("codogram.handlers.finish.require_claude_ready", new_callable=AsyncMock, return_value=True):
                with patch("codogram.handlers.finish.archive_thread") as mock_archive:
                    mock_archive.return_value = True
                    await cmd_finish(mock_message, mock_queue)

        # Should show warning about stale worktree
        call_args = mock_queue.reply.call_args_list
        messages = [str(call[0][1] if len(call[0]) > 1 else call[1].get("text", "")) for call in call_args]
        assert any("[!]" in msg and "not found" in msg.lower() for msg in messages), f"Expected stale warning in: {messages}"

        # Should still archive
        mock_archive.assert_called_once()
