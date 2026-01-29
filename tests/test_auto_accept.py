import pytest
from unittest.mock import AsyncMock, MagicMock
from codogram.auto_accept import select_option, try_auto_accept, AUTO_ACCEPT_TYPES
from codogram.claude.screen import PromptType
from codogram.strings import SNIP


def _make_mock_thread(thread_id=None, last_tool_msg_text=None):
    """Create mock thread for testing."""
    mock = MagicMock()
    mock.thread_id = thread_id
    mock.last_tool_msg_text = last_tool_msg_text
    mock.auto_accept_count = 0
    mock.settings = {}
    # Set thread-level settings to None so get_thread_setting falls back to global defaults
    # (MagicMock returns MagicMock for any attribute, not None)
    mock.display_mode = None
    mock.line_limit = None
    return mock


# Tests for select_option
def test_select_option_picks_yes():
    assert select_option(["1. Yes", "2. Allow all"]) == "1"

def test_select_option_picks_allow_once():
    assert select_option(["1. Allow once", "2. No"]) == "1"

def test_select_option_skips_session_wide():
    assert select_option(["1. Allow for session", "2. No"]) is None

def test_select_option_skips_all():
    assert select_option(["1. Yes, allow all edits", "2. No"]) is None

def test_select_option_no_match():
    assert select_option(["1. src/main.py"]) is None

def test_select_option_empty():
    assert select_option([]) is None

# Tests for try_auto_accept
@pytest.mark.asyncio
async def test_try_auto_accept_success():
    tmux = MagicMock()
    queue = AsyncMock()
    thread = _make_mock_thread()

    result = await try_auto_accept(
        options=["1. Yes", "2. No"],
        body="Run command: git status",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        context_name="test-project",
        thread=thread,
    )

    assert result is True
    tmux.send_key.assert_called_once_with("1")
    queue.enqueue_nowait.assert_called_once()

@pytest.mark.asyncio
async def test_try_auto_accept_no_safe_option():
    tmux = MagicMock()
    queue = AsyncMock()
    thread = _make_mock_thread()

    result = await try_auto_accept(
        options=["1. Allow for session", "2. No"],
        body="Some prompt",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        context_name="test-project",
        thread=thread,
    )

    assert result is False
    tmux.send_key.assert_not_called()
    queue.enqueue_nowait.assert_not_called()

@pytest.mark.asyncio
async def test_try_auto_accept_empty_body():
    tmux = MagicMock()
    queue = AsyncMock()
    thread = _make_mock_thread(thread_id=456)

    result = await try_auto_accept(
        options=["1. Yes"],
        body=None,
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        context_name="test-thread",
        thread=thread,
    )

    assert result is True
    call_args = queue.enqueue_nowait.call_args[0][0]
    assert "[no details]" in call_args.messages[0]["text"]


# Tests for prompt type whitelist
def test_auto_accept_types_whitelist():
    """Only REGULAR prompts should be auto-accepted."""
    assert PromptType.REGULAR in AUTO_ACCEPT_TYPES
    assert PromptType.TRUST_PROMPT not in AUTO_ACCEPT_TYPES


@pytest.mark.asyncio
async def test_try_auto_accept_skips_mcp_trust():
    """MCP trust prompts should not be auto-accepted."""
    tmux = MagicMock()
    queue = AsyncMock()
    thread = _make_mock_thread()

    result = await try_auto_accept(
        options=["1. Yes", "2. No"],  # Would normally be accepted
        body="Allow MCP server?",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        context_name="test-project",
        prompt_type=PromptType.TRUST_PROMPT,
        thread=thread,
    )

    assert result is False
    tmux.send_key.assert_not_called()
    queue.enqueue_nowait.assert_not_called()


@pytest.mark.asyncio
async def test_try_auto_accept_truncates_in_short_mode():
    """Body should be truncated with default line_limit."""
    tmux = MagicMock()
    queue = AsyncMock()
    thread = _make_mock_thread()
    # Explicitly set display_mode to "lines" to test truncation
    # (global config may have different display_mode)
    thread.display_mode = "lines"

    long_body = "\n".join([f"line{i}" for i in range(10)])

    result = await try_auto_accept(
        options=["1. Yes"],
        body=long_body,
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        context_name="test",
        thread=thread,
    )

    assert result is True
    call_args = queue.enqueue_nowait.call_args[0][0]
    sent_text = call_args.messages[0]["text"]
    assert SNIP in sent_text


@pytest.mark.asyncio
async def test_try_auto_accept_inline_edit():
    """When last_tool_msg_text exists, should edit message instead of sending new."""
    tmux = MagicMock()
    queue = AsyncMock()
    thread = _make_mock_thread(last_tool_msg_text="○ Read: file.py")

    result = await try_auto_accept(
        options=["1. Yes"],
        body="Read file",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        context_name="test",
        thread=thread,
    )

    assert result is True
    # Should call enqueue (for edit), not enqueue_nowait (for new message)
    queue.enqueue.assert_called_once()
    queue.enqueue_nowait.assert_not_called()
    # Check suffix was added
    assert thread.auto_accept_count == 1
