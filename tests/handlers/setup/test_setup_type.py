# tests/handlers/setup/test_setup_type.py
"""Tests for setup type callback handlers."""
import os
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

import pytest

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from aiogram.types import CallbackQuery, Message, Chat
from aiogram.fsm.context import FSMContext

from codogram.handlers.setup.setup_type import (
    on_clone_selected,
    on_connect_selected,
    on_new_selected,
)
from codogram.domain.states import SetupFlow
from codogram import strings


@pytest.fixture
def mock_message():
    """Create mock message for callback."""
    message = Mock(spec=Message)
    message.chat = Mock(spec=Chat)
    message.chat.id = -1001234567890
    message.date = datetime.now(timezone.utc)
    message.edit_text = AsyncMock()
    return message


@pytest.fixture
def mock_callback(mock_message):
    """Create mock callback query."""
    callback = Mock(spec=CallbackQuery)
    callback.message = mock_message
    callback.answer = AsyncMock()
    callback.data = "setup:clone"
    callback.bot = AsyncMock()
    return callback


@pytest.fixture
def mock_state():
    """Create mock FSM state."""
    state = Mock(spec=FSMContext)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


class TestOnCloneSelected:
    """Tests for Clone repository selection."""

    @pytest.mark.asyncio
    async def test_clone_selected_transitions_to_awaiting_clone_url(
        self, mock_callback, mock_state
    ):
        """Clone selection transitions to awaiting_clone_url state."""
        mock_callback.data = "setup:clone"

        await on_clone_selected(mock_callback, mock_state)

        mock_state.set_state.assert_called_once_with(SetupFlow.awaiting_clone_url)

    @pytest.mark.asyncio
    async def test_clone_selected_stores_setup_type(self, mock_callback, mock_state):
        """Clone selection stores setup_type in state data."""
        mock_callback.data = "setup:clone"

        await on_clone_selected(mock_callback, mock_state)

        mock_state.update_data.assert_called_once_with(setup_type="clone")

    @pytest.mark.asyncio
    async def test_clone_selected_shows_url_prompt(self, mock_callback, mock_state):
        """Clone selection shows URL prompt message."""
        mock_callback.data = "setup:clone"

        await on_clone_selected(mock_callback, mock_state)

        mock_callback.message.edit_text.assert_called_once()
        call_args = mock_callback.message.edit_text.call_args
        assert call_args[0][0] == strings.SETUP_CLONE_URL_PROMPT

    @pytest.mark.asyncio
    async def test_clone_selected_shows_go_back_button(self, mock_callback, mock_state):
        """Clone selection shows keyboard with Go back button."""
        mock_callback.data = "setup:clone"

        await on_clone_selected(mock_callback, mock_state)

        call_args = mock_callback.message.edit_text.call_args
        reply_markup = call_args[1]["reply_markup"]
        buttons = [btn for row in reply_markup.inline_keyboard for btn in row]

        assert len(buttons) == 1
        assert buttons[0].text == strings.BTN_GO_BACK
        assert buttons[0].callback_data == "clone:back"

    @pytest.mark.asyncio
    async def test_clone_selected_acknowledges_callback(self, mock_callback, mock_state):
        """Clone selection acknowledges the callback."""
        mock_callback.data = "setup:clone"

        await on_clone_selected(mock_callback, mock_state)

        mock_callback.answer.assert_called_once()


class TestOnConnectSelected:
    """Tests for Connect to existing folder selection."""

    @pytest.mark.asyncio
    async def test_connect_selected_transitions_to_folder_select(
        self, mock_callback, mock_state
    ):
        """Connect selection transitions to awaiting_folder_select state."""
        mock_callback.data = "setup:connect"

        with patch(
            "codogram.handlers.setup.connect_flow.show_folder_selection"
        ) as mock_show:
            mock_show.return_value = None
            await on_connect_selected(mock_callback, mock_state)

        mock_state.set_state.assert_called_once_with(SetupFlow.awaiting_folder_select)

    @pytest.mark.asyncio
    async def test_connect_selected_stores_setup_type(self, mock_callback, mock_state):
        """Connect selection stores setup_type in state data."""
        mock_callback.data = "setup:connect"

        with patch(
            "codogram.handlers.setup.connect_flow.show_folder_selection"
        ) as mock_show:
            mock_show.return_value = None
            await on_connect_selected(mock_callback, mock_state)

        mock_state.update_data.assert_called_once_with(setup_type="connect")

    @pytest.mark.asyncio
    async def test_connect_selected_calls_show_folder_selection(
        self, mock_callback, mock_state
    ):
        """Connect selection calls show_folder_selection with page=0."""
        mock_callback.data = "setup:connect"

        with patch(
            "codogram.handlers.setup.connect_flow.show_folder_selection"
        ) as mock_show:
            mock_show.return_value = None
            await on_connect_selected(mock_callback, mock_state)

        mock_show.assert_called_once_with(mock_callback.message, mock_state, page=0)

    @pytest.mark.asyncio
    async def test_connect_selected_acknowledges_callback(
        self, mock_callback, mock_state
    ):
        """Connect selection acknowledges the callback."""
        mock_callback.data = "setup:connect"

        with patch(
            "codogram.handlers.setup.connect_flow.show_folder_selection"
        ) as mock_show:
            mock_show.return_value = None
            await on_connect_selected(mock_callback, mock_state)

        mock_callback.answer.assert_called_once()


class TestOnNewSelected:
    """Tests for Start new project selection."""

    @pytest.mark.asyncio
    async def test_new_selected_transitions_to_awaiting_project_name(
        self, mock_callback, mock_state
    ):
        """New project selection transitions to awaiting_project_name state."""
        mock_callback.data = "setup:new"

        with patch(
            "codogram.handlers.setup.new_project_flow.show_project_name_prompt"
        ) as mock_show:
            mock_show.return_value = None
            await on_new_selected(mock_callback, mock_state)

        mock_state.set_state.assert_called_once_with(SetupFlow.awaiting_project_name)

    @pytest.mark.asyncio
    async def test_new_selected_stores_setup_type(self, mock_callback, mock_state):
        """New project selection stores setup_type in state data."""
        mock_callback.data = "setup:new"

        with patch(
            "codogram.handlers.setup.new_project_flow.show_project_name_prompt"
        ) as mock_show:
            mock_show.return_value = None
            await on_new_selected(mock_callback, mock_state)

        mock_state.update_data.assert_called_once_with(setup_type="new")

    @pytest.mark.asyncio
    async def test_new_selected_calls_show_project_name_prompt(
        self, mock_callback, mock_state
    ):
        """New project selection calls show_project_name_prompt."""
        mock_callback.data = "setup:new"

        with patch(
            "codogram.handlers.setup.new_project_flow.show_project_name_prompt"
        ) as mock_show:
            mock_show.return_value = None
            await on_new_selected(mock_callback, mock_state)

        mock_show.assert_called_once_with(mock_callback.message, mock_state)

    @pytest.mark.asyncio
    async def test_new_selected_acknowledges_callback(self, mock_callback, mock_state):
        """New project selection acknowledges the callback."""
        mock_callback.data = "setup:new"

        with patch(
            "codogram.handlers.setup.new_project_flow.show_project_name_prompt"
        ) as mock_show:
            mock_show.return_value = None
            await on_new_selected(mock_callback, mock_state)

        mock_callback.answer.assert_called_once()
