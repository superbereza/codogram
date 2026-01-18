# tests/middleware/test_setup_blocker.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from codogram.middleware.setup_blocker import SetupBlockerMiddleware


@pytest.mark.asyncio
async def test_allows_start_during_setup():
    """Commands /start, /reset_all, /help, /get_debug_ids allowed during setup."""
    middleware = SetupBlockerMiddleware()

    # Mock handler
    handler = AsyncMock()

    # Mock message with /start command
    message = MagicMock()
    message.text = "/start"

    # Mock state with SetupFlow active
    state = AsyncMock()
    state.get_state = AsyncMock(return_value="SetupFlow:awaiting_setup_type")

    data = {"state": state}

    await middleware(handler, message, data)

    # Handler should be called
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_blocks_other_commands_during_setup():
    """Other commands blocked during setup."""
    middleware = SetupBlockerMiddleware()

    handler = AsyncMock()

    message = MagicMock()
    message.text = "/settings"
    message.answer = AsyncMock()

    state = AsyncMock()
    state.get_state = AsyncMock(return_value="SetupFlow:awaiting_setup_type")

    data = {"state": state}

    await middleware(handler, message, data)

    # Handler should NOT be called
    handler.assert_not_called()
    # Should send blocking message
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_allows_all_commands_outside_setup():
    """All commands allowed when not in setup."""
    middleware = SetupBlockerMiddleware()

    handler = AsyncMock()

    message = MagicMock()
    message.text = "/settings"

    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)

    data = {"state": state}

    await middleware(handler, message, data)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_allows_non_commands_during_setup():
    """Regular messages allowed during setup (for text input)."""
    middleware = SetupBlockerMiddleware()

    handler = AsyncMock()

    message = MagicMock()
    message.text = "my-project-name"  # Not a command

    state = AsyncMock()
    state.get_state = AsyncMock(return_value="SetupFlow:awaiting_project_name")

    data = {"state": state}

    await middleware(handler, message, data)

    handler.assert_called_once()
