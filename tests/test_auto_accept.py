import pytest
from unittest.mock import AsyncMock, MagicMock
from codogram.auto_accept import select_option, try_auto_accept, AUTO_ACCEPT_TYPES
from codogram.screen import PromptType
from codogram.strings import SNIP

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

    result = await try_auto_accept(
        options=["1. Yes", "2. No"],
        body="Run command: git status",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test-project",
    )

    assert result is True
    tmux.send_key.assert_called_once_with("1")
    queue.enqueue_nowait.assert_called_once()

@pytest.mark.asyncio
async def test_try_auto_accept_no_safe_option():
    tmux = MagicMock()
    queue = AsyncMock()

    result = await try_auto_accept(
        options=["1. Allow for session", "2. No"],
        body="Some prompt",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test-project",
    )

    assert result is False
    tmux.send_key.assert_not_called()
    queue.enqueue_nowait.assert_not_called()

@pytest.mark.asyncio
async def test_try_auto_accept_empty_body():
    tmux = MagicMock()
    queue = AsyncMock()

    result = await try_auto_accept(
        options=["1. Yes"],
        body=None,
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=456,
        context_name="test-thread",
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

    result = await try_auto_accept(
        options=["1. Yes", "2. No"],  # Would normally be accepted
        body="Allow MCP server?",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test-project",
        prompt_type=PromptType.TRUST_PROMPT,
    )

    assert result is False
    tmux.send_key.assert_not_called()
    queue.enqueue_nowait.assert_not_called()


@pytest.mark.asyncio
async def test_try_auto_accept_truncates_in_short_mode():
    """Body should be truncated when verbose=False."""
    tmux = MagicMock()
    queue = AsyncMock()

    long_body = "\n".join([f"line{i}" for i in range(10)])

    result = await try_auto_accept(
        options=["1. Yes"],
        body=long_body,
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test",
        verbose=False,
    )

    assert result is True
    call_args = queue.enqueue_nowait.call_args[0][0]
    sent_text = call_args.messages[0]["text"]
    assert SNIP in sent_text
