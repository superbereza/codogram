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


def make_flood_error(retry_after: int = 0):
    """Create TelegramRetryAfter exception.

    Note: retry_after is in seconds. Using 0 for tests to avoid delays.
    The implementation accesses e.retry_after directly.
    """
    from aiogram.exceptions import TelegramRetryAfter
    error = TelegramRetryAfter(method=Mock(), message="Flood control", retry_after=retry_after)
    return error


@pytest.mark.asyncio
async def test_cleanup_orphans_on_flood(queue, mock_bot):
    """Orphan messages deleted when flood control hits mid-batch."""
    mock_bot.send_message = AsyncMock(side_effect=[
        Mock(message_id=100),
        Mock(message_id=101),
        make_flood_error(0),  # Flood on 3rd message (0s delay for test speed)
        # Retry succeeds
        Mock(message_id=200),
        Mock(message_id=201),
        Mock(message_id=202),
    ])

    batch = OutgoingBatch(1, None, [{"text": "a"}, {"text": "b"}, {"text": "c"}])
    msg_ids = await queue.enqueue(batch)

    # Should have deleted the 2 orphan messages (100, 101)
    assert mock_bot.delete_message.call_count == 2
    # Should return IDs from successful retry
    assert msg_ids == [200, 201, 202]
    await queue.shutdown()


@pytest.mark.asyncio
async def test_separate_queues_per_chat(queue, mock_bot):
    """Each chat_id has independent queue and worker."""
    await queue.enqueue(OutgoingBatch(111, None, [{"text": "a"}]))
    await queue.enqueue(OutgoingBatch(222, None, [{"text": "b"}]))

    assert len(queue._workers) == 2
    await queue.shutdown()


@pytest.mark.asyncio
async def test_enqueue_nowait_does_not_block(queue, mock_bot):
    """enqueue_nowait returns immediately without waiting for send."""
    send_started = asyncio.Event()
    send_complete = asyncio.Event()

    async def slow_send(**kw):
        send_started.set()
        await send_complete.wait()
        return Mock(message_id=1)

    mock_bot.send_message = AsyncMock(side_effect=slow_send)

    # enqueue_nowait should return before send completes
    await queue.enqueue_nowait(OutgoingBatch(1, None, [{"text": "slow"}]))

    # Verify send started but we didn't wait for it
    await asyncio.sleep(0.01)
    assert send_started.is_set()

    # Complete the send
    send_complete.set()
    await asyncio.sleep(0.01)
    await queue.shutdown()


@pytest.mark.asyncio
async def test_max_retries_exhausted(queue, mock_bot):
    """Returns empty list after max retry attempts."""
    mock_bot.send_message = AsyncMock(side_effect=make_flood_error(0))

    batch = OutgoingBatch(1, None, [{"text": "fail"}])
    msg_ids = await queue.enqueue(batch)

    assert msg_ids == []
    await queue.shutdown()


@pytest.mark.asyncio
async def test_lock_prevents_duplicate_workers(queue, mock_bot):
    """Concurrent enqueues don't create duplicate workers."""
    # Slow down send to increase race window
    async def slow_send(**kw):
        await asyncio.sleep(0.01)
        return Mock(message_id=1)
    mock_bot.send_message = AsyncMock(side_effect=slow_send)

    # Launch many concurrent enqueues
    tasks = [
        asyncio.create_task(queue.enqueue(OutgoingBatch(1, None, [{"text": f"msg{i}"}])))
        for i in range(10)
    ]
    await asyncio.gather(*tasks)

    # Should only have 1 worker for chat_id=1
    assert len(queue._workers) == 1
    await queue.shutdown()
