"""Tests for start handlers."""
import os
from unittest.mock import Mock, AsyncMock, patch

import pytest

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from aiogram.types import Message, Chat
from aiogram.fsm.context import FSMContext

from codogram.handlers.start import cmd_start
from codogram.services.start_flow import FlowAction


@pytest.fixture
def mock_message():
    """Create mock message."""
    message = Mock(spec=Message)
    message.chat = Mock(spec=Chat)
    message.chat.id = 123
    message.chat.title = "Test Chat"
    message.text = "/start"
    message.message_thread_id = None
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_state():
    """Create mock FSM state."""
    state = Mock(spec=FSMContext)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


class TestCmdStart:
    """Tests for /start command."""

    @pytest.mark.asyncio
    async def test_start_no_project_no_title_asks_name(self, mock_message, mock_state):
        """No project and no chat title -> asks for project name."""
        mock_message.chat.title = None  # No chat title

        with patch("codogram.handlers.start.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = None

            await cmd_start(mock_message, mock_state)

        mock_state.set_state.assert_called_once()
        mock_message.answer.assert_called_once()
        # Should ask for project name
        call_args = mock_message.answer.call_args[0][0].lower()
        assert "проект" in call_args or "имя" in call_args
