"""Tests for /finish command."""
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
def require_claude_ready_patch():
    """Patch require_claude_ready to return True."""
    async def _mock(*args, **kwargs):
        return True
    return patch("codogram.handlers.finish.require_claude_ready", side_effect=_mock)


@pytest.mark.asyncio
async def test_finish_in_regular_topic_shows_confirmation(mock_message, require_claude_ready_patch):
    """In regular topic (no worktree), /finish should show archive confirmation."""
    from codogram.handlers.finish import cmd_finish

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_thread = MagicMock()
    mock_thread.worktree_path = None  # Regular topic
    mock_thread.name = "test-thread"
    mock_project.threads = {456: mock_thread}
    mock_project.get_thread = MagicMock(return_value=mock_thread)

    with require_claude_ready_patch, \
         patch("codogram.handlers.finish.project_manager") as mock_pm:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_finish(mock_message, mock_queue)

        # Should show confirmation with "Archive" in text
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Archive" in call_args[0][1]


@pytest.mark.asyncio
async def test_finish_in_general_shows_nothing_to_finish(mock_message, require_claude_ready_patch):
    """In General (thread_id=None), /finish should suggest /clear."""
    from codogram.handlers.finish import cmd_finish

    mock_message.message_thread_id = None
    mock_queue = AsyncMock()

    with require_claude_ready_patch:
        await cmd_finish(mock_message, mock_queue)

    mock_queue.reply.assert_called_once()
    call_args = mock_queue.reply.call_args
    assert "Nothing to finish" in call_args[0][1]
