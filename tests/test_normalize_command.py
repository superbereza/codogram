"""Tests for NormalizeCommandMiddleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock, create_autospec

from aiogram.types import Message

from codogram.middleware.normalize_command import NormalizeCommandMiddleware


@pytest.fixture
def middleware():
    return NormalizeCommandMiddleware()


@pytest.fixture
def mock_handler():
    return AsyncMock()


def make_message(text: str) -> Message:
    """Create a mock Message with given text."""
    msg = create_autospec(Message, instance=True)
    msg.text = text
    return msg


@pytest.mark.asyncio
async def test_lowercase_command(middleware, mock_handler):
    """Command should be lowercased."""
    msg = make_message("/Branch")
    await middleware(mock_handler, msg, {})

    assert msg.text == "/branch"
    mock_handler.assert_called_once()


@pytest.mark.asyncio
async def test_uppercase_command(middleware, mock_handler):
    """All-caps command should be lowercased."""
    msg = make_message("/HELP")
    await middleware(mock_handler, msg, {})

    assert msg.text == "/help"


@pytest.mark.asyncio
async def test_mixed_case_command(middleware, mock_handler):
    """Mixed case command should be lowercased."""
    msg = make_message("/BrAnCh_CrEaTe")
    await middleware(mock_handler, msg, {})

    assert msg.text == "/branch_create"


@pytest.mark.asyncio
async def test_command_with_args_preserves_case(middleware, mock_handler):
    """Arguments should preserve their original case."""
    msg = make_message("/branch MyFeature")
    await middleware(mock_handler, msg, {})

    assert msg.text == "/branch MyFeature"


@pytest.mark.asyncio
async def test_uppercase_command_with_args(middleware, mock_handler):
    """Command lowercased, args preserved."""
    msg = make_message("/BRANCH MyFeature with CAPS")
    await middleware(mock_handler, msg, {})

    assert msg.text == "/branch MyFeature with CAPS"


@pytest.mark.asyncio
async def test_already_lowercase(middleware, mock_handler):
    """Already lowercase command unchanged."""
    msg = make_message("/help")
    await middleware(mock_handler, msg, {})

    assert msg.text == "/help"


@pytest.mark.asyncio
async def test_regular_message_unchanged(middleware, mock_handler):
    """Non-command messages unchanged."""
    msg = make_message("Hello World")
    await middleware(mock_handler, msg, {})

    assert msg.text == "Hello World"


@pytest.mark.asyncio
async def test_empty_text_unchanged(middleware, mock_handler):
    """Empty text handled gracefully."""
    msg = make_message("")
    msg.text = ""
    await middleware(mock_handler, msg, {})

    assert msg.text == ""


@pytest.mark.asyncio
async def test_none_text_unchanged(middleware, mock_handler):
    """None text handled gracefully."""
    msg = MagicMock()
    msg.text = None
    await middleware(mock_handler, msg, {})

    assert msg.text is None


@pytest.mark.asyncio
async def test_non_message_event_unchanged(middleware, mock_handler):
    """Non-Message events pass through unchanged."""
    event = MagicMock()  # Not a Message
    event.text = "/BRANCH"

    # Should not modify non-Message events
    await middleware(mock_handler, event, {})

    # text unchanged because it's not a Message instance
    assert event.text == "/BRANCH"
