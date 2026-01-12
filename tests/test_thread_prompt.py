"""Tests for /thread command name prompt behavior."""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Message, Chat

from codogram.handlers.common import get_flow_state, clear_flow_state


@pytest.fixture
def mock_message():
    """Create mock message for forum group."""
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.chat.is_forum = True
    msg.message_thread_id = 456
    msg.bot = MagicMock()
    return msg


@pytest.fixture
def mock_project():
    """Create mock project."""
    project = MagicMock()
    project.threads = {}
    return project


@pytest.fixture(autouse=True)
def cleanup_flow_state():
    """Clean up flow state after each test."""
    yield
    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_thread_without_arg_shows_prompt(mock_message, mock_project):
    """Test /thread without argument shows name prompt with buttons."""
    from codogram.handlers.threads import cmd_thread_create

    mock_message.text = "/thread"
    mock_queue = AsyncMock()

    with patch("codogram.handlers.threads.project_manager") as mock_pm:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_thread_create(mock_message, mock_queue)

    # Check flow state was set
    state = get_flow_state(-100123, 456)
    assert state is not None
    assert state["type"] == "awaiting_create_name"
    assert state["create_type"] == "thread"

    # Check reply was sent with keyboard
    mock_queue.reply.assert_called_once()
    call_args = mock_queue.reply.call_args
    assert "Thread name?" in call_args[0][1]
    assert call_args[1].get("reply_markup") is not None


@pytest.mark.asyncio
async def test_thread_with_name_validates_and_creates(mock_message, mock_project):
    """Test /thread mystic validates and creates directly."""
    from codogram.handlers.threads import cmd_thread_create

    mock_message.text = "/thread mystic"
    mock_queue = AsyncMock()

    with patch("codogram.handlers.threads.project_manager") as mock_pm, \
         patch("codogram.handlers.threads.create_thread_with_session") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_create.return_value = MagicMock()  # Successful thread creation

        await cmd_thread_create(mock_message, mock_queue)

    # No flow state should be set (direct creation)
    state = get_flow_state(-100123, 456)
    assert state is None

    # Thread should be created directly
    mock_create.assert_called_once()
    assert mock_create.call_args[1]["name"] == "mystic"


@pytest.mark.asyncio
async def test_thread_with_invalid_name_shows_error(mock_message, mock_project):
    """Test /thread with invalid name shows error."""
    from codogram.handlers.threads import cmd_thread_create

    mock_message.text = "/thread !!!"
    mock_queue = AsyncMock()

    with patch("codogram.handlers.threads.project_manager") as mock_pm, \
         patch("codogram.handlers.threads.create_thread_with_session") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_thread_create(mock_message, mock_queue)

    # Error should be shown
    mock_queue.reply.assert_called_once()
    assert "Invalid" in mock_queue.reply.call_args[0][1]

    # Thread should NOT be created
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_thread_with_empty_arg_shows_prompt(mock_message, mock_project):
    """Test /thread with empty/whitespace arg shows prompt."""
    from codogram.handlers.threads import cmd_thread_create

    mock_message.text = "/thread   "  # Just whitespace
    mock_queue = AsyncMock()

    with patch("codogram.handlers.threads.project_manager") as mock_pm:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_thread_create(mock_message, mock_queue)

    # Check flow state was set (prompt shown)
    state = get_flow_state(-100123, 456)
    assert state is not None
    assert state["type"] == "awaiting_create_name"
