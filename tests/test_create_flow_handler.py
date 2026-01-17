"""Tests for create flow handler."""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import CallbackQuery, Message, Chat

from codogram.handlers.common import set_flow_state, get_flow_state, clear_flow_state


@pytest.fixture
def mock_callback():
    cb = MagicMock(spec=CallbackQuery)
    cb.message = MagicMock(spec=Message)
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = -100123
    cb.message.message_thread_id = 456
    cb.message.delete = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.message_thread_id = 456
    msg.text = "my-feature"
    msg.bot = MagicMock()
    return msg


@pytest.mark.asyncio
async def test_cancel_deletes_message_and_clears_state(mock_callback):
    """Cancel callback deletes prompt and clears state."""
    from codogram.handlers.create_flow import on_create_cancel

    mock_callback.data = "create_cancel"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name"})

    mock_queue = AsyncMock()

    await on_create_cancel(mock_callback, mock_queue)

    assert get_flow_state(-100123, 456) is None
    mock_callback.message.delete.assert_called_once()
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_magic_branch_creates_branch(mock_callback):
    """Magic name callback creates branch with random name."""
    from codogram.handlers.create_flow import on_create_magic

    mock_callback.data = "create_magic:branch"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "branch"})

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.threads = {}

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service, \
         patch("codogram.handlers.create_flow._do_create_branch") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.get_magic_name.return_value = "arcane"

        await on_create_magic(mock_callback, mock_queue)

        assert get_flow_state(-100123, 456) is None
        mock_queue.edit.assert_called_once()  # Shows "Creating..." status
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_magic_thread_creates_thread(mock_callback):
    """Magic name callback creates thread with random name."""
    from codogram.handlers.create_flow import on_create_magic

    mock_callback.data = "create_magic:thread"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "thread"})

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.threads = {}

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service, \
         patch("codogram.handlers.create_flow._do_create_thread") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.get_magic_name.return_value = "mystic"

        await on_create_magic(mock_callback, mock_queue)

        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_handle_name_input_creates_branch(mock_message):
    """Text message creates branch when awaiting."""
    from codogram.handlers.create_flow import handle_name_input

    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "branch"})

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.threads = {}

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service, \
         patch("codogram.handlers.create_flow._do_create_branch") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.validate_name.return_value = ("my-feature", None)

        result = await handle_name_input(mock_message, mock_queue)

        assert result is True
        assert get_flow_state(-100123, 456) is None
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_handle_name_input_invalid_shows_error(mock_message):
    """Invalid name shows error."""
    from codogram.handlers.create_flow import handle_name_input

    mock_message.text = "!!!"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "branch"})

    mock_queue = AsyncMock()
    mock_project = MagicMock()

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.validate_name.return_value = (None, "`[x]` Invalid name")

        result = await handle_name_input(mock_message, mock_queue)

        assert result is True
        mock_queue.reply.assert_called_once()
        assert "Invalid" in mock_queue.reply.call_args[0][1]

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_handle_name_input_no_state_returns_false(mock_message):
    """Returns False if no awaiting state."""
    from codogram.handlers.create_flow import handle_name_input

    clear_flow_state(-100123, 456)

    mock_queue = AsyncMock()

    result = await handle_name_input(mock_message, mock_queue)

    assert result is False
