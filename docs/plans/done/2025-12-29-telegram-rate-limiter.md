# Telegram Rate Limiter Implementation Plan (v2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement rate-limited FIFO message queue for Telegram API to prevent flood control errors across multiple pollers while preserving button handler cleanup.

**Architecture:** Single TelegramQueue instance, FIFO queue per chat_id with worker auto-start/stop. Two enqueue modes: `enqueue()` returns message IDs (for permission_poller), `enqueue_nowait()` is fire-and-forget (for watcher).

**Tech Stack:** Python 3.11+, asyncio, aiogram 3.x, pytest

---

## Review Fixes Applied

| Issue | Solution |
|-------|----------|
| `create_watcher_task` не существует | Создаём функцию, исправляем dead code в main.py |
| permission_messages ломается | `enqueue()` возвращает `list[int]` с message IDs |
| Race condition в enqueue | `asyncio.Lock` per chat_id |
| history_watcher.py не детализирован | Явные шаги для каждого call site |
| Нет graceful shutdown | Добавляем вызов в main.py |

---

## Task 1: Create TelegramQueue with dataclass

**Files:**
- Create: `src/codogram/telegram_queue.py`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write test for OutgoingBatch**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_queue.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create telegram_queue.py**

```python
# src/codogram/telegram_queue.py
"""Rate-limited Telegram message queue with FIFO ordering per chat_id."""
import asyncio
from collections import defaultdict
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from .logging_config import logger


@dataclass
class OutgoingBatch:
    """Batch of messages to send atomically."""
    chat_id: int
    thread_id: int | None
    messages: list[dict]  # [{text, parse_mode, reply_markup?}, ...]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_telegram_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(telegram_queue): add OutgoingBatch dataclass"
```

---

## Task 2: Implement TelegramQueue with enqueue() returning IDs

**Files:**
- Modify: `src/codogram/telegram_queue.py`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write tests for enqueue with ID return**

```python
# tests/test_telegram_queue.py (append)
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_queue.py::test_enqueue_returns_message_ids -v`
Expected: FAIL with "TelegramQueue not found"

**Step 3: Implement TelegramQueue class**

```python
# src/codogram/telegram_queue.py (append after OutgoingBatch)


@dataclass
class _QueueItem:
    """Internal queue item with result future."""
    batch: OutgoingBatch
    result: asyncio.Future  # Future[list[int]]


class TelegramQueue:
    """FIFO queue for outgoing messages per chat_id.

    Thread-safe: uses locks to prevent race conditions when starting workers.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self._queues: dict[int, asyncio.Queue[_QueueItem]] = defaultdict(asyncio.Queue)
        self._workers: dict[int, asyncio.Task] = {}
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def enqueue(self, batch: OutgoingBatch) -> list[int]:
        """Add batch to queue, wait for send, return message IDs.

        Use this when you need to track sent message IDs (e.g., for cleanup).
        """
        chat_id = batch.chat_id
        result_future: asyncio.Future[list[int]] = asyncio.get_event_loop().create_future()
        item = _QueueItem(batch=batch, result=result_future)

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

        await self._queues[chat_id].put(item)
        return await result_future

    async def enqueue_nowait(self, batch: OutgoingBatch) -> None:
        """Add batch to queue without waiting. Fire-and-forget.

        Use this when you don't need message IDs (e.g., watcher notifications).
        """
        chat_id = batch.chat_id
        result_future: asyncio.Future[list[int]] = asyncio.get_event_loop().create_future()
        item = _QueueItem(batch=batch, result=result_future)

        async with self._locks[chat_id]:
            if chat_id not in self._workers or self._workers[chat_id].done():
                self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))

        await self._queues[chat_id].put(item)
        # Don't await result - fire and forget

    async def _worker(self, chat_id: int) -> None:
        """Process queue FIFO. Exits after 5 min idle."""
        queue = self._queues[chat_id]

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=300)
            except asyncio.TimeoutError:
                logger.debug(f"Queue worker {chat_id} exiting (idle timeout)")
                return

            try:
                sent_ids = await self._send_batch(item.batch)
                if not item.result.done():
                    item.result.set_result(sent_ids)
            except Exception as e:
                if not item.result.done():
                    item.result.set_exception(e)
            finally:
                queue.task_done()

    async def _send_batch(self, batch: OutgoingBatch, attempt: int = 0) -> list[int]:
        """Send all messages in batch. Returns message IDs. Cleanup on failure."""
        MAX_ATTEMPTS = 3

        if attempt >= MAX_ATTEMPTS:
            logger.error(f"Failed to send after {MAX_ATTEMPTS} attempts, chat_id={batch.chat_id}")
            return []

        sent_ids: list[int] = []

        try:
            for msg in batch.messages:
                result = await self.bot.send_message(
                    chat_id=batch.chat_id,
                    message_thread_id=batch.thread_id,
                    **msg,
                )
                sent_ids.append(result.message_id)
            return sent_ids

        except TelegramRetryAfter as e:
            await self._cleanup_orphans(batch.chat_id, sent_ids)
            logger.warning(f"Rate limited chat_id={batch.chat_id}, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            return await self._send_batch(batch, attempt + 1)

        except TelegramBadRequest as e:
            await self._cleanup_orphans(batch.chat_id, sent_ids)
            logger.warning(f"BadRequest chat_id={batch.chat_id}: {e}")
            return []

    async def _cleanup_orphans(self, chat_id: int, msg_ids: list[int]) -> None:
        """Delete partially sent messages."""
        for msg_id in msg_ids:
            try:
                await self.bot.delete_message(chat_id, msg_id)
            except Exception:
                pass

    async def shutdown(self) -> None:
        """Stop all workers gracefully."""
        for task in self._workers.values():
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)
        self._workers.clear()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(telegram_queue): implement TelegramQueue with enqueue() returning IDs"
```

---

## Task 3: Add tests for error handling and enqueue_nowait

**Files:**
- Test: `tests/test_telegram_queue.py`

**Step 1: Write comprehensive tests**

```python
# tests/test_telegram_queue.py (append)

def make_flood_error(retry_after: float):
    """Create TelegramRetryAfter exception."""
    from aiogram.exceptions import TelegramRetryAfter
    error = TelegramRetryAfter(method=Mock(), message="Flood control")
    error.retry_after = retry_after
    return error


@pytest.mark.asyncio
async def test_cleanup_orphans_on_flood(queue, mock_bot):
    """Orphan messages deleted when flood control hits mid-batch."""
    mock_bot.send_message = AsyncMock(side_effect=[
        Mock(message_id=100),
        Mock(message_id=101),
        make_flood_error(0.01),  # Flood on 3rd message
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
    mock_bot.send_message = AsyncMock(side_effect=make_flood_error(0.001))

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
```

**Step 2: Run tests**

Run: `pytest tests/test_telegram_queue.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_telegram_queue.py
git commit -m "test(telegram_queue): add error handling and concurrency tests"
```

---

## Task 4: Create create_watcher_task function (fix dead code)

**Files:**
- Modify: `src/codogram/watcher.py`

**Step 1: Add create_watcher_task at end of watcher.py**

```python
# src/codogram/watcher.py (append at end)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue


async def create_watcher_task(
    bot: Bot,
    project,
    telegram_queue: "TelegramQueue",
    send_missed: bool = False,
) -> asyncio.Task:
    """Create jsonl watcher task for project's main thread.

    This is a compatibility shim - actual watching is done per-thread
    via watch_thread_jsonl in history_watcher.py.
    """
    from .session_manager import ProjectState

    if not isinstance(project, ProjectState):
        raise TypeError("project must be ProjectState")

    # Get or create main thread
    main_thread = project.get_or_create_thread(None, "main")

    if not main_thread.jsonl_path:
        # No session yet, return a no-op task
        async def noop():
            pass
        return asyncio.create_task(noop())

    # Create watcher for main thread
    return asyncio.create_task(
        _watch_with_queue(bot, project, main_thread, telegram_queue)
    )


async def _watch_with_queue(bot: Bot, project, thread, telegram_queue: "TelegramQueue"):
    """Watch jsonl and send entries through queue."""
    from .telegram_queue import OutgoingBatch
    from pathlib import Path

    if not thread.jsonl_path:
        return

    watcher = JsonlWatcher(Path(thread.jsonl_path))

    try:
        async for entry in watcher.watch():
            try:
                messages = _entry_to_messages(entry)
                if messages:
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    await telegram_queue.enqueue_nowait(batch)
            except Exception as e:
                logger.warning(f"watch_with_queue error: {e}")
    except asyncio.CancelledError:
        raise


def _entry_to_messages(entry: ParsedEntry) -> list[dict]:
    """Convert ParsedEntry to list of message dicts for queue."""
    messages = []

    if entry.content_type == ContentType.TEXT:
        for chunk in chunk_message(entry.text):
            messages.append({"text": f"● {chunk}", "parse_mode": "Markdown"})

    elif entry.content_type == ContentType.TOOL_USE:
        text = format_tool_use(entry.tool_name, entry.tool_input)
        messages.append({"text": text, "parse_mode": "Markdown"})

    return messages
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/watcher.py`
Expected: No errors

**Step 3: Verify import works**

Run: `python3 -c "from codogram.watcher import create_watcher_task; print('OK')"`
Expected: "OK"

**Step 4: Commit**

```bash
git add src/codogram/watcher.py
git commit -m "feat(watcher): add create_watcher_task function"
```

---

## Task 5: Integrate TelegramQueue into main.py

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Add import**

At top of file, add:
```python
from .telegram_queue import TelegramQueue
```

**Step 2: Add module-level variable**

Before `async def main():`, add:
```python
telegram_queue: TelegramQueue | None = None
```

**Step 3: Create queue in main()**

After `bot = Bot(token=settings.telegram_token)`, add:
```python
    global telegram_queue
    telegram_queue = TelegramQueue(bot)
```

**Step 4: Update start_poller to pass queue**

Change:
```python
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project, telegram_queue)
```

**Step 5: Update start_watcher to pass queue**

Change:
```python
    async def start_watcher(project: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project, telegram_queue, send_missed)
```

**Step 6: Add graceful shutdown**

Wrap `await dp.start_polling(bot)` in try/finally:
```python
    try:
        await dp.start_polling(bot)
    finally:
        if telegram_queue:
            await telegram_queue.shutdown()
```

**Step 7: Verify syntax**

Run: `python3 -m py_compile src/codogram/main.py`
Expected: No errors

**Step 8: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(main): integrate TelegramQueue with graceful shutdown"
```

---

## Task 6: Update permission_poller signatures

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Add imports at top**

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue
```

**Step 2: Update create_poller_task signature**

Change:
```python
async def create_poller_task(bot: Bot, project: ProjectState, telegram_queue: "TelegramQueue") -> asyncio.Task:
    """Create permission poller task for project."""
    return asyncio.create_task(permission_poller_for_project(bot, project, telegram_queue))
```

**Step 3: Update permission_poller_for_project signature**

Change:
```python
async def permission_poller_for_project(bot: Bot, project: ProjectState, telegram_queue: "TelegramQueue"):
```

**Step 4: Update create_poller_task_for_thread signature**

Change:
```python
async def create_poller_task_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue") -> asyncio.Task:
    """Create permission poller task for a specific thread."""
    return asyncio.create_task(permission_poller_for_thread(bot, project, thread, telegram_queue))
```

**Step 5: Update permission_poller_for_thread signature**

Change:
```python
async def permission_poller_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue"):
```

**Step 6: Verify syntax**

Run: `python3 -m py_compile src/codogram/permission_poller.py`
Expected: No errors

**Step 7: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "refactor(permission_poller): add telegram_queue parameter"
```

---

## Task 7: Replace direct sends with queue in permission_poller_for_project

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Add OutgoingBatch import**

Add to imports:
```python
from .telegram_queue import OutgoingBatch
```

**Step 2: Replace DEBOUNCING→SHOWING send block (lines ~96-145)**

Find the block starting with `if elapsed >= DEBOUNCE_TIME:` and replace the send logic:

```python
                if elapsed >= DEBOUNCE_TIME:
                    logger.debug(f"Poller DEBOUNCING→SHOWING: sending to Telegram")
                    logger.debug(f"Poller: body preview: {parsed.body[:200]}...")
                    try:
                        # Build batch of body messages
                        body_messages = []
                        if parsed.body:
                            body_text = SEPARATOR_SOLID + "\n" + parsed.body
                            for chunk in chunk_message(body_text):
                                body_messages.append({"text": chunk, "parse_mode": "Markdown"})

                        # Options as text
                        options_text = "\n".join(parsed.options)
                        body_messages.append({"text": options_text})

                        # Send body through queue, get IDs for cleanup
                        batch = OutgoingBatch(
                            chat_id=chat_id,
                            thread_id=None,
                            messages=body_messages,
                        )
                        content_msg_ids = await telegram_queue.enqueue(batch)

                        # Keyboard sent directly (need to track for button handler)
                        kb = permission_keyboard(parsed.options, project.tmux_session)
                        kb_msg = await bot.send_message(chat_id, "👆", reply_markup=kb)
                        permission_messages[kb_msg.message_id] = content_msg_ids

                        state = PollerState.SHOWING
                        last_body = parsed.body
                        logger.debug(f"Poller SHOWING: sent {len(parsed.options)} options, kb_msg={kb_msg.message_id}")
                    except Exception as e:
                        logger.warning(f"Permission poller: send error: {e}")
                        state = PollerState.IDLE
```

**Step 3: Update SHOWING cleanup when permission disappears (lines ~147-167)**

```python
        elif state == PollerState.SHOWING:
            if not is_permission:
                logger.debug("Poller SHOWING→IDLE: permission gone, cleaning up")
                # Cleanup messages
                if kb_msg and kb_msg.message_id in permission_messages:
                    for msg_id in permission_messages[kb_msg.message_id]:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                    try:
                        await bot.delete_message(chat_id, kb_msg.message_id)
                    except Exception:
                        pass
                    permission_messages.pop(kb_msg.message_id, None)

                state = PollerState.IDLE
                last_options = None
                last_body = None
                content_msg_ids = []
                kb_msg = None
```

**Step 4: Update SHOWING resend block (lines ~168-231)**

```python
            elif parsed.options != last_options or parsed.body != last_body:
                logger.debug(f"Poller SHOWING: body/options changed, resending")
                try:
                    # Delete old messages
                    if kb_msg and kb_msg.message_id in permission_messages:
                        for msg_id in permission_messages[kb_msg.message_id]:
                            try:
                                await bot.delete_message(chat_id, msg_id)
                            except Exception:
                                pass
                        try:
                            await bot.delete_message(chat_id, kb_msg.message_id)
                        except Exception:
                            pass
                        permission_messages.pop(kb_msg.message_id, None)

                    # Build new body messages
                    body_messages = []
                    if parsed.body:
                        body_text = SEPARATOR_SOLID + "\n" + parsed.body
                        for chunk in chunk_message(body_text):
                            body_messages.append({"text": chunk, "parse_mode": "Markdown"})

                    options_text = "\n".join(parsed.options)
                    body_messages.append({"text": options_text})

                    # Send through queue
                    batch = OutgoingBatch(chat_id=chat_id, thread_id=None, messages=body_messages)
                    content_msg_ids = await telegram_queue.enqueue(batch)

                    # Keyboard directly
                    kb = permission_keyboard(parsed.options, project.tmux_session)
                    kb_msg = await bot.send_message(chat_id, "👆", reply_markup=kb)
                    permission_messages[kb_msg.message_id] = content_msg_ids

                    last_options = parsed.options
                    last_body = parsed.body
                except Exception as e:
                    logger.warning(f"Poller SHOWING: resend error: {e}")
```

**Step 5: Verify syntax**

Run: `python3 -m py_compile src/codogram/permission_poller.py`
Expected: No errors

**Step 6: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "refactor(permission_poller): use queue for body sends in project poller"
```

---

## Task 8: Apply same changes to permission_poller_for_thread

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Apply identical pattern to thread poller**

In `permission_poller_for_thread`, apply the same changes as Task 7:
- Replace direct sends in DEBOUNCING→SHOWING with `telegram_queue.enqueue(batch)`
- Keep keyboard send direct
- Update cleanup and resend blocks

Key difference: use `thread_id=thread_id` instead of `thread_id=None`

```python
                        batch = OutgoingBatch(
                            chat_id=chat_id,
                            thread_id=thread_id,
                            messages=body_messages,
                        )
                        content_msg_ids = await telegram_queue.enqueue(batch)

                        kb = permission_keyboard(parsed.options, tmux_name)
                        kb_msg = await bot.send_message(
                            chat_id, "👆", reply_markup=kb, message_thread_id=thread_id
                        )
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/permission_poller.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "refactor(permission_poller): use queue for body sends in thread poller"
```

---

## Task 9: Update history_watcher.py to use queue

**Files:**
- Modify: `src/codogram/history_watcher.py`

**Step 1: Add imports**

At top, add:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue
```

**Step 2: Update HistoryWatcher.__init__ to accept queue**

```python
class HistoryWatcher:
    """Watches history.jsonl for session changes."""

    def __init__(self, bot: Bot, start_poller, start_watcher, telegram_queue: "TelegramQueue"):
        self.bot = bot
        self.start_poller = start_poller
        self.start_watcher = start_watcher
        self.telegram_queue = telegram_queue
        self.project_manager = project_manager
        self._last_mtime = 0
        self._task: asyncio.Task | None = None
```

**Step 3: Update notification sends to use queue**

In `_check_for_changes`, update the "session closed" notification (lines ~98-105):

```python
                    # Notify user through queue
                    from .telegram_queue import OutgoingBatch
                    try:
                        batch = OutgoingBatch(
                            chat_id=project.chat_id,
                            thread_id=thread.thread_id,
                            messages=[{"text": f"⚠️ Claude session closed: {thread.name}"}],
                        )
                        await self.telegram_queue.enqueue_nowait(batch)
                    except Exception:
                        pass
```

**Step 4: Update watch_thread_jsonl to use queue**

```python
async def watch_thread_jsonl(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue"):
    """Watch jsonl for a specific thread and send messages through queue."""
    from .watcher import JsonlWatcher, _entry_to_messages
    from .telegram_queue import OutgoingBatch
    from pathlib import Path

    if not thread.jsonl_path:
        return

    watcher = JsonlWatcher(Path(thread.jsonl_path))

    try:
        async for entry in watcher.watch():
            try:
                messages = _entry_to_messages(entry)
                if messages:
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    await telegram_queue.enqueue_nowait(batch)
            except Exception as e:
                logger.error("watch_thread_error", extra={"error": str(e)})
    except asyncio.CancelledError:
        logger.info(f"watch_thread_cancelled: thread={thread.name}")
        raise
```

**Step 5: Update poll_for_session_thread to use queue**

Add telegram_queue parameter and update the timeout notification (lines ~214-221):

```python
async def poll_for_session_thread(
    project: ProjectState,
    thread: ThreadInfo,
    bot: Bot,
    start_poller,
    start_watcher,
    telegram_queue: "TelegramQueue",
) -> None:
```

Update timeout notification:
```python
    # Timeout
    logger.warning(f"poll_for_session_thread_timeout: project={project.project_name}, thread={thread.name}")
    thread.awaiting_new_session = False
    try:
        from .telegram_queue import OutgoingBatch
        batch = OutgoingBatch(
            chat_id=project.chat_id,
            thread_id=thread.thread_id,
            messages=[{"text": "⚠️ Сессия не обнаружена. Проверьте что Claude запущен."}],
        )
        await telegram_queue.enqueue_nowait(batch)
    except Exception:
        pass
```

**Step 6: Update create_history_watcher**

```python
async def create_history_watcher(bot: Bot, start_poller, start_watcher, telegram_queue: "TelegramQueue") -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher, telegram_queue)
    await watcher.start()
    return watcher
```

**Step 7: Update watcher task creation in poll_for_session_thread**

Line ~194-196:
```python
                if not thread.watcher_task or thread.watcher_task.done():
                    thread.watcher_task = asyncio.create_task(
                        watch_thread_jsonl(bot, project, thread, telegram_queue)
                    )
```

**Step 8: Verify syntax**

Run: `python3 -m py_compile src/codogram/history_watcher.py`
Expected: No errors

**Step 9: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "refactor(history_watcher): use telegram_queue for all sends"
```

---

## Task 10: Update main.py to pass queue to history_watcher

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Update create_history_watcher call**

Change:
```python
    await create_history_watcher(bot, start_poller, start_watcher, telegram_queue)
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/main.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(main): pass telegram_queue to history_watcher"
```

---

## Task 11: Update bot.py callers

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Find all call sites**

Run: `grep -n "create_poller_task\|start_poller\|start_watcher\|poll_for_session" src/codogram/bot.py`

**Step 2: Update _make_task_starters to include queue**

Find `_make_task_starters` and update to:

```python
def _make_task_starters(bot: Bot):
    """Create task starter functions with bot and queue bound."""
    from .main import telegram_queue

    async def start_poller(project):
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project, telegram_queue)

    async def start_watcher(project, send_missed=False):
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project, telegram_queue, send_missed)

    return start_poller, start_watcher
```

**Step 3: Update calls to poll_for_session_thread**

Find all calls to `poll_for_session_thread` and add `telegram_queue` parameter:

```python
from .main import telegram_queue

thread.binding_task = asyncio.create_task(
    poll_for_session_thread(project, thread, message.bot, start_poller, start_watcher, telegram_queue)
)
```

**Step 4: Update calls to create_poller_task_for_thread**

Find and update:
```python
from .main import telegram_queue

thread.poller_task = await create_poller_task_for_thread(bot, project, thread, telegram_queue)
```

**Step 5: Verify syntax**

Run: `python3 -m py_compile src/codogram/bot.py`
Expected: No errors

**Step 6: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): pass telegram_queue to all poller/watcher calls"
```

---

## Task 12: Run full test suite

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 2: Fix any failures**

If tests fail due to signature changes, update mocks:

```python
# Example fix for test_permission_poller.py
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_telegram_queue():
    queue = Mock()
    queue.enqueue = AsyncMock(return_value=[1, 2, 3])
    queue.enqueue_nowait = AsyncMock()
    return queue
```

**Step 3: Commit fixes**

```bash
git add -A
git commit -m "fix: update tests for telegram_queue integration"
```

---

## Task 13: Manual testing

**Step 1: Start the bot**

Run: `./restart.sh`

**Step 2: Test permission polling**

1. Start Claude session that will ask for permission
2. Verify permission prompt appears in Telegram
3. Click button, verify cleanup works
4. Check logs for "Rate limited" - should not appear in normal operation

**Step 3: Test concurrent threads**

1. Create 3+ topics with active Claude sessions
2. Trigger permissions simultaneously
3. Verify no flood control errors
4. Verify all messages arrive and cleanup works

**Step 4: Check logs**

Run: `tail -100 ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log | grep -E "(Rate limited|Flood|error)"`
Expected: No errors during normal operation

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found in manual testing"
```

---

## Summary

| Task | Description | Key Change |
|------|-------------|------------|
| 1 | Create OutgoingBatch | New file |
| 2 | TelegramQueue with enqueue() returning IDs | Core feature |
| 3 | Error handling tests | Tests |
| 4 | Create create_watcher_task (fix dead code) | watcher.py |
| 5 | Integrate queue into main.py | main.py |
| 6 | Update permission_poller signatures | Signatures only |
| 7 | Queue sends in project poller | Body через queue, keyboard напрямую |
| 8 | Queue sends in thread poller | Same pattern |
| 9 | Queue sends in history_watcher | All notifications |
| 10 | Wire queue to history_watcher | main.py |
| 11 | Update bot.py callers | All call sites |
| 12 | Run tests | Verification |
| 13 | Manual testing | Verification |

**Key Design Decision:** `enqueue()` blocks and returns message IDs, preserving `permission_messages` tracking for button handler cleanup. Body messages go through queue (rate limiting), keyboard message goes direct (need immediate ID).
