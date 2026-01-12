"""Tests for clear create state middleware."""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat

from codogram.middleware.clear_create_state import ClearCreateStateMiddleware
from codogram.handlers.common import set_flow_state, get_flow_state, clear_flow_state


@pytest.fixture
def middleware():
    return ClearCreateStateMiddleware()


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.message_thread_id = 456
    msg.text = "/help"
    return msg


@pytest.mark.asyncio
async def test_clears_create_state_on_command(middleware, mock_message):
    """Command clears awaiting_create_name state."""
    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "branch"})

    handler = AsyncMock()
    await middleware(handler, mock_message, {})

    assert get_flow_state(-100123, 456) is None
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_does_not_clear_other_state_types(middleware, mock_message):
    """Command does not clear other state types."""
    set_flow_state(-100123, 456, {"type": "thread_create_pending", "name": "test"})

    handler = AsyncMock()
    await middleware(handler, mock_message, {})

    state = get_flow_state(-100123, 456)
    assert state is not None
    assert state["type"] == "thread_create_pending"

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_does_not_affect_non_commands(middleware, mock_message):
    """Non-command messages don't trigger state clearing."""
    mock_message.text = "regular message"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name"})

    handler = AsyncMock()
    await middleware(handler, mock_message, {})

    assert get_flow_state(-100123, 456) is not None

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_handles_none_text(middleware, mock_message):
    """Handles messages with no text (images, etc)."""
    mock_message.text = None
    set_flow_state(-100123, 456, {"type": "awaiting_create_name"})

    handler = AsyncMock()
    await middleware(handler, mock_message, {})

    # State should remain since no text to check
    assert get_flow_state(-100123, 456) is not None
    handler.assert_called_once()

    clear_flow_state(-100123, 456)
