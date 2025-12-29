# tests/test_telegram_queue.py
import pytest
from codogram.telegram_queue import OutgoingBatch


def test_outgoing_batch_creation():
    batch = OutgoingBatch(
        chat_id=123,
        thread_id=456,
        messages=[{"text": "hello", "parse_mode": "Markdown"}]
    )
    assert batch.chat_id == 123
    assert batch.thread_id == 456
    assert len(batch.messages) == 1


def test_outgoing_batch_without_thread():
    batch = OutgoingBatch(chat_id=123, thread_id=None, messages=[{"text": "hi"}])
    assert batch.thread_id is None


# TelegramQueue tests
import asyncio
from unittest.mock import Mock, AsyncMock
from aiogram import Bot
from codogram.telegram_queue import TelegramQueue


@pytest.fixture
def mock_bot():
    bot = Mock(spec=Bot)
    bot.send_message = AsyncMock(return_value=Mock(message_id=1))
    bot.delete_message = AsyncMock()
    return bot


@pytest.fixture
def queue(mock_bot):
    return TelegramQueue(mock_bot)


@pytest.mark.asyncio
async def test_enqueue_returns_message_ids(queue, mock_bot):
    """Enqueue should return list of sent message IDs."""
    call_count = 0
    async def mock_send(**kw):
        nonlocal call_count
        call_count += 1
        return Mock(message_id=100 + call_count)
    mock_bot.send_message = AsyncMock(side_effect=mock_send)

    batch = OutgoingBatch(123, None, [{"text": "a"}, {"text": "b"}])
    msg_ids = await queue.enqueue(batch)

    assert msg_ids == [101, 102]
    await queue.shutdown()


@pytest.mark.asyncio
async def test_enqueue_starts_worker(queue):
    """Enqueue should start worker for chat_id."""
    batch = OutgoingBatch(123, None, [{"text": "hello"}])
    await queue.enqueue(batch)

    assert 123 in queue._workers
    await queue.shutdown()


@pytest.mark.asyncio
async def test_fifo_order(queue, mock_bot):
    """Messages sent in FIFO order."""
    results = []
    async def capture_send(**kw):
        results.append(kw["text"])
        return Mock(message_id=len(results))
    mock_bot.send_message = AsyncMock(side_effect=capture_send)

    # Enqueue two batches concurrently
    task1 = asyncio.create_task(queue.enqueue(OutgoingBatch(1, None, [{"text": "first"}])))
    task2 = asyncio.create_task(queue.enqueue(OutgoingBatch(1, None, [{"text": "second"}])))

    await asyncio.gather(task1, task2)
    await queue.shutdown()

    assert results == ["first", "second"]
