"""Tests for handlers/common.py helper functions."""
import os

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_require_tmux_exists_no_project():
    """require_tmux_exists returns False when project not found."""
    from codogram.handlers.common import require_tmux_exists

    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    with patch('codogram.handlers.common.project_manager') as pm:
        pm.get_by_chat.return_value = None

        result = await require_tmux_exists(message, queue)

        assert result is False
        queue.reply.assert_called_once()


@pytest.mark.asyncio
async def test_require_tmux_exists_no_cwd():
    """require_tmux_exists returns False when project has no cwd."""
    from codogram.handlers.common import require_tmux_exists

    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    project = MagicMock()
    project.cwd = None

    with patch('codogram.handlers.common.project_manager') as pm:
        pm.get_by_chat.return_value = project

        result = await require_tmux_exists(message, queue)

        assert result is False
        queue.reply.assert_called_once()


@pytest.mark.asyncio
async def test_require_tmux_exists_no_thread():
    """require_tmux_exists returns False when thread not found."""
    from codogram.handlers.common import require_tmux_exists

    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = 456
    queue = AsyncMock()

    project = MagicMock()
    project.cwd = "/test"
    project.threads = {}  # No threads

    with patch('codogram.handlers.common.project_manager') as pm:
        pm.get_by_chat.return_value = project

        result = await require_tmux_exists(message, queue)

        assert result is False
        queue.reply.assert_called_once()


@pytest.mark.asyncio
async def test_require_tmux_exists_no_tmux_session():
    """require_tmux_exists returns False when tmux session doesn't exist."""
    from codogram.handlers.common import require_tmux_exists

    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    project = MagicMock()
    project.cwd = "/test"
    project.project_name = "test"
    thread = MagicMock()
    thread.get_tmux_session.return_value = "claude-test"
    project.threads = {None: thread}

    with patch('codogram.handlers.common.project_manager') as pm, \
         patch('codogram.handlers.common.is_tmux_session_exists') as tmux_exists:

        pm.get_by_chat.return_value = project
        tmux_exists.return_value = False

        result = await require_tmux_exists(message, queue)

        assert result is False
        queue.reply.assert_called_once()


@pytest.mark.asyncio
async def test_require_tmux_exists_success():
    """require_tmux_exists returns True when all conditions met."""
    from codogram.handlers.common import require_tmux_exists

    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    project = MagicMock()
    project.cwd = "/test"
    project.project_name = "test"
    thread = MagicMock()
    thread.get_tmux_session.return_value = "claude-test"
    project.threads = {None: thread}

    with patch('codogram.handlers.common.project_manager') as pm, \
         patch('codogram.handlers.common.is_tmux_session_exists') as tmux_exists:

        pm.get_by_chat.return_value = project
        tmux_exists.return_value = True

        result = await require_tmux_exists(message, queue)

        assert result is True
        queue.reply.assert_not_called()


@pytest.mark.asyncio
async def test_require_claude_ready_tmux_not_ready():
    """require_claude_ready returns False when Claude is not ready."""
    from codogram.handlers.common import require_claude_ready

    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    project = MagicMock()
    project.cwd = "/test"
    project.project_name = "test"
    thread = MagicMock()
    thread.get_tmux_session.return_value = "claude-test"
    project.threads = {None: thread}

    with patch('codogram.handlers.common.project_manager') as pm, \
         patch('codogram.handlers.common.is_tmux_session_exists') as tmux_exists, \
         patch('codogram.handlers.common.TmuxSession') as TmuxClass:

        pm.get_by_chat.return_value = project
        tmux_exists.return_value = True
        tmux_instance = MagicMock()
        tmux_instance.is_claude_ready.return_value = False
        TmuxClass.return_value = tmux_instance

        result = await require_claude_ready(message, queue)

        assert result is False
        # Should have called reply for "Claude is starting"
        queue.reply.assert_called_once()


@pytest.mark.asyncio
async def test_require_claude_ready_success():
    """require_claude_ready returns True when Claude is ready."""
    from codogram.handlers.common import require_claude_ready

    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    project = MagicMock()
    project.cwd = "/test"
    project.project_name = "test"
    thread = MagicMock()
    thread.get_tmux_session.return_value = "claude-test"
    project.threads = {None: thread}

    with patch('codogram.handlers.common.project_manager') as pm, \
         patch('codogram.handlers.common.is_tmux_session_exists') as tmux_exists, \
         patch('codogram.handlers.common.TmuxSession') as TmuxClass:

        pm.get_by_chat.return_value = project
        tmux_exists.return_value = True
        tmux_instance = MagicMock()
        tmux_instance.is_claude_ready.return_value = True
        TmuxClass.return_value = tmux_instance

        result = await require_claude_ready(message, queue)

        assert result is True
        queue.reply.assert_not_called()


@pytest.mark.asyncio
async def test_require_claude_ready_fails_on_tmux_check():
    """require_claude_ready returns False when tmux check fails."""
    from codogram.handlers.common import require_claude_ready

    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    with patch('codogram.handlers.common.project_manager') as pm:
        pm.get_by_chat.return_value = None

        result = await require_claude_ready(message, queue)

        assert result is False
        queue.reply.assert_called_once()
