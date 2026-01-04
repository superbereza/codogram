# tests/test_telegram_queue_edit.py
"""Tests for EditBatch functionality in TelegramQueue."""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from codogram.telegram_queue import TelegramQueue, EditBatch


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=Mock(message_id=1))
    bot.delete_message = AsyncMock()
    return bot


@pytest.fixture
def queue(mock_bot):
    return TelegramQueue(mock_bot)


def test_edit_batch_creation():
    """EditBatch should store all fields correctly."""
    batch = EditBatch(
        chat_id=123,
        message_id=456,
        text="edited text",
        parse_mode="Markdown",
    )
    assert batch.chat_id == 123
    assert batch.message_id == 456
    assert batch.text == "edited text"
    assert batch.parse_mode == "Markdown"


def test_edit_batch_default_parse_mode():
    """EditBatch parse_mode should default to None."""
    batch = EditBatch(chat_id=123, message_id=456, text="text")
    assert batch.parse_mode is None


@pytest.mark.asyncio
async def test_edit_batch_calls_edit_message_text(queue, mock_bot):
    """EditBatch should call bot.edit_message_text."""
    await queue.enqueue(EditBatch(
        chat_id=123,
        message_id=456,
        text="edited text",
        parse_mode="Markdown",
    ))

    mock_bot.edit_message_text.assert_called_once_with(
        chat_id=123,
        message_id=456,
        text="edited text",
        parse_mode="Markdown",
        reply_markup=None,
    )
    await queue.shutdown()


@pytest.mark.asyncio
async def test_edit_batch_returns_none(queue, mock_bot):
    """enqueue(EditBatch) should return None."""
    result = await queue.enqueue(EditBatch(
        chat_id=123,
        message_id=456,
        text="edited text",
    ))

    assert result is None
    await queue.shutdown()


@pytest.mark.asyncio
async def test_edit_batch_nowait(queue, mock_bot):
    """enqueue_nowait should work with EditBatch."""
    await queue.enqueue_nowait(EditBatch(
        chat_id=123,
        message_id=456,
        text="edited text",
    ))

    # Give worker time to process
    await asyncio.sleep(0.01)

    mock_bot.edit_message_text.assert_called_once()
    await queue.shutdown()


def make_flood_error(retry_after: int = 0):
    """Create TelegramRetryAfter exception."""
    error = TelegramRetryAfter(method=Mock(), message="Flood control", retry_after=retry_after)
    return error


def make_parse_error():
    """Create TelegramBadRequest for parse errors."""
    error = TelegramBadRequest(method=Mock(), message="Can't parse entities")
    return error


@pytest.mark.asyncio
async def test_edit_batch_retry_on_flood(queue, mock_bot):
    """EditBatch should retry on TelegramRetryAfter."""
    mock_bot.edit_message_text = AsyncMock(side_effect=[
        make_flood_error(0),  # First attempt fails
        None,  # Retry succeeds
    ])

    await queue.enqueue(EditBatch(
        chat_id=123,
        message_id=456,
        text="edited text",
    ))

    assert mock_bot.edit_message_text.call_count == 2
    await queue.shutdown()


@pytest.mark.asyncio
async def test_edit_batch_retry_without_parse_mode_on_error(queue, mock_bot):
    """EditBatch should retry without parse_mode on parse error."""
    mock_bot.edit_message_text = AsyncMock(side_effect=[
        make_parse_error(),  # First attempt fails with parse error
        None,  # Retry without parse_mode succeeds
    ])

    await queue.enqueue(EditBatch(
        chat_id=123,
        message_id=456,
        text="edited text",
        parse_mode="Markdown",
    ))

    assert mock_bot.edit_message_text.call_count == 2
    # Second call should have parse_mode=None
    second_call = mock_bot.edit_message_text.call_args_list[1]
    assert second_call.kwargs["parse_mode"] is None
    await queue.shutdown()


@pytest.mark.asyncio
async def test_edit_batch_max_retries_exhausted(queue, mock_bot):
    """EditBatch should stop after max retry attempts."""
    mock_bot.edit_message_text = AsyncMock(side_effect=make_flood_error(0))

    # Should not raise, just log error
    await queue.enqueue(EditBatch(
        chat_id=123,
        message_id=456,
        text="edited text",
    ))

    # 3 attempts max
    assert mock_bot.edit_message_text.call_count == 3
    await queue.shutdown()


@pytest.mark.asyncio
async def test_edit_batch_deleted_message_ignored(queue, mock_bot):
    """EditBatch should ignore errors when message is deleted."""
    error = TelegramBadRequest(method=Mock(), message="Message not found")
    mock_bot.edit_message_text = AsyncMock(side_effect=error)

    # Should not raise
    await queue.enqueue(EditBatch(
        chat_id=123,
        message_id=456,
        text="edited text",
    ))

    assert mock_bot.edit_message_text.call_count == 1
    await queue.shutdown()


@pytest.mark.asyncio
async def test_edit_and_send_use_same_queue(queue, mock_bot):
    """Edit and send operations should go through the same per-chat queue."""
    from codogram.telegram_queue import OutgoingBatch

    results = []

    async def capture_send(**kw):
        results.append(("send", kw.get("text")))
        return Mock(message_id=1)

    async def capture_edit(**kw):
        results.append(("edit", kw.get("text")))

    mock_bot.send_message = AsyncMock(side_effect=capture_send)
    mock_bot.edit_message_text = AsyncMock(side_effect=capture_edit)

    # Enqueue operations concurrently
    await asyncio.gather(
        queue.enqueue(OutgoingBatch(1, None, [{"text": "send1"}])),
        queue.enqueue(EditBatch(1, 100, "edit1")),
        queue.enqueue(OutgoingBatch(1, None, [{"text": "send2"}])),
    )

    # All operations should be processed in FIFO order
    assert len(results) == 3
    assert results[0] == ("send", "send1")
    assert results[1] == ("edit", "edit1")
    assert results[2] == ("send", "send2")
    await queue.shutdown()
