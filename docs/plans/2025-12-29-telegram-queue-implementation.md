# Telegram Queue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement rate-limited message queue for Telegram API to prevent flood control errors.

**Architecture:** FIFO queue per chat_id with worker that handles send/edit operations, cleanup orphans on errors, and retry with backoff.

**Tech Stack:** Python 3.11+, asyncio, aiogram 3.x, pytest

---

## Task 1: Create TelegramQueue module

**Files:**
- Create: `src/codogram/telegram_queue.py`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write test for OutgoingBatch dataclass**

```python
# tests/test_telegram_queue.py
import pytest
from codogram.telegram_queue import OutgoingBatch, EditBatch

def test_outgoing_batch_creation():
    batch = OutgoingBatch(
        chat_id=123,
        thread_id=456,
        messages=[{"text": "hello", "parse_mode": "Markdown"}]
    )
    assert batch.chat_id == 123
    assert batch.thread_id == 456
    assert len(batch.messages) == 1

def test_edit_batch_creation():
    batch = EditBatch(
        chat_id=123,
        message_id=789,
        text="updated",
        parse_mode="Markdown"
    )
    assert batch.chat_id == 123
    assert batch.message_id == 789
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_queue.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create telegram_queue.py with dataclasses**

```python
# src/codogram/telegram_queue.py
"""Rate-limited Telegram message queue."""
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Union

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from .logging_config import logger


@dataclass
class OutgoingBatch:
    """Batch of messages to send atomically."""
    chat_id: int
    thread_id: int | None
    messages: list[dict]  # [{text, parse_mode, reply_markup?}, ...]


@dataclass
class EditBatch:
    """Single message edit operation."""
    chat_id: int
    message_id: int
    text: str
    parse_mode: str | None = None


QueueItem = Union[OutgoingBatch, EditBatch]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_telegram_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(telegram_queue): add OutgoingBatch and EditBatch dataclasses"
```

---

## Task 2: Implement TelegramQueue class

**Files:**
- Modify: `src/codogram/telegram_queue.py`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write test for enqueue and worker**

```python
# tests/test_telegram_queue.py (append)
from unittest.mock import Mock, AsyncMock
from codogram.telegram_queue import TelegramQueue

@pytest.fixture
def mock_bot():
    bot = Mock(spec=Bot)
    bot.send_message = AsyncMock(return_value=Mock(message_id=1))
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    return bot

@pytest.fixture
def queue(mock_bot):
    return TelegramQueue(mock_bot)

@pytest.mark.asyncio
async def test_enqueue_starts_worker(queue):
    """Enqueue should start worker for chat_id."""
    batch = OutgoingBatch(123, None, [{"text": "hello"}])
    await queue.enqueue(batch)

    assert 123 in queue._workers
    assert not queue._workers[123].done()

    # Cleanup
    await queue.shutdown()

@pytest.mark.asyncio
async def test_fifo_order(queue, mock_bot):
    """Messages sent in order they were enqueued."""
    results = []
    async def capture_send(**kw):
        results.append(kw["text"])
        return Mock(message_id=len(results))
    mock_bot.send_message = AsyncMock(side_effect=capture_send)

    await queue.enqueue(OutgoingBatch(1, None, [{"text": "first"}]))
    await queue.enqueue(OutgoingBatch(1, None, [{"text": "second"}]))

    # Wait for queue to process
    await asyncio.sleep(0.1)
    await queue._queues[1].join()

    assert results == ["first", "second"]
    await queue.shutdown()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_queue.py::test_enqueue_starts_worker -v`
Expected: FAIL with "TelegramQueue has no attribute"

**Step 3: Implement TelegramQueue class**

```python
# src/codogram/telegram_queue.py (append after dataclasses)

class TelegramQueue:
    """FIFO queue for outgoing messages per chat_id."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._queues: dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._workers: dict[int, asyncio.Task] = {}

    async def enqueue(self, item: QueueItem) -> None:
        """Add item to queue. Starts worker if needed."""
        chat_id = item.chat_id

        if chat_id not in self._workers or self._workers[chat_id].done():
            self._workers[chat_id] = asyncio.create_task(
                self._worker(chat_id)
            )

        await self._queues[chat_id].put(item)

    async def _worker(self, chat_id: int) -> None:
        """Process queue FIFO."""
        queue = self._queues[chat_id]

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=300)
            except asyncio.TimeoutError:
                return  # Exit, will restart on next enqueue

            await self._process_item(item)
            queue.task_done()

    async def _process_item(self, item: QueueItem) -> None:
        """Route item to appropriate handler."""
        if isinstance(item, OutgoingBatch):
            await self._send_batch(item)
        elif isinstance(item, EditBatch):
            await self._edit_message(item)

    async def _send_batch(self, batch: OutgoingBatch, attempt: int = 0) -> None:
        """Send all messages in batch. Cleanup on failure."""
        MAX_ATTEMPTS = 3

        if attempt >= MAX_ATTEMPTS:
            logger.error(f"Failed to send after {MAX_ATTEMPTS} attempts")
            return

        sent_ids: list[int] = []

        try:
            for msg in batch.messages:
                result = await self.bot.send_message(
                    chat_id=batch.chat_id,
                    message_thread_id=batch.thread_id,
                    **msg,
                )
                sent_ids.append(result.message_id)

        except TelegramRetryAfter as e:
            await self._cleanup_orphans(batch.chat_id, sent_ids)
            logger.warning(f"Rate limited, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            await self._send_batch(batch, attempt + 1)

        except TelegramBadRequest as e:
            await self._cleanup_orphans(batch.chat_id, sent_ids)
            logger.warning(f"Cannot send to {batch.chat_id}: {e}")

    async def _edit_message(self, item: EditBatch, attempt: int = 0) -> None:
        """Edit a message. Retry on rate limit."""
        MAX_ATTEMPTS = 3

        if attempt >= MAX_ATTEMPTS:
            logger.error(f"Failed to edit after {MAX_ATTEMPTS} attempts")
            return

        try:
            await self.bot.edit_message_text(
                chat_id=item.chat_id,
                message_id=item.message_id,
                text=item.text,
                parse_mode=item.parse_mode,
            )
        except TelegramRetryAfter as e:
            logger.warning(f"Rate limited on edit, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            await self._edit_message(item, attempt + 1)
        except TelegramBadRequest:
            pass  # Message deleted or can't be edited, ignore

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
        await asyncio.gather(*self._workers.values(), return_exceptions=True)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(telegram_queue): implement TelegramQueue with FIFO processing"
```

---

## Task 3: Add tests for error handling

**Files:**
- Test: `tests/test_telegram_queue.py`

**Step 1: Write test for orphan cleanup on flood**

```python
# tests/test_telegram_queue.py (append)

def make_flood_error(retry_after: float):
    """Create TelegramRetryAfter exception."""
    from aiogram.exceptions import TelegramRetryAfter
    error = TelegramRetryAfter(method=Mock(), message=f"Flood control: retry after {retry_after}")
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
    await queue.enqueue(batch)

    await asyncio.sleep(0.2)
    await queue._queues[1].join()

    # Should have deleted the 2 orphan messages (100, 101)
    assert mock_bot.delete_message.call_count == 2
    await queue.shutdown()

@pytest.mark.asyncio
async def test_separate_queues_per_chat(queue, mock_bot):
    """Each chat_id has independent queue."""
    await queue.enqueue(OutgoingBatch(111, None, [{"text": "a"}]))
    await queue.enqueue(OutgoingBatch(222, None, [{"text": "b"}]))

    await asyncio.sleep(0.1)

    assert len(queue._workers) == 2
    await queue.shutdown()

@pytest.mark.asyncio
async def test_edit_batch_processed(queue, mock_bot):
    """EditBatch calls edit_message_text."""
    await queue.enqueue(EditBatch(123, 456, "new text", "Markdown"))

    await asyncio.sleep(0.1)
    await queue._queues[123].join()

    mock_bot.edit_message_text.assert_called_once_with(
        chat_id=123,
        message_id=456,
        text="new text",
        parse_mode="Markdown",
    )
    await queue.shutdown()
```

**Step 2: Run tests**

Run: `pytest tests/test_telegram_queue.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_telegram_queue.py
git commit -m "test(telegram_queue): add error handling and edit tests"
```

---

## Task 4: Integrate TelegramQueue into main.py

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Add TelegramQueue creation**

```python
# src/codogram/main.py
# Add import at top:
from .telegram_queue import TelegramQueue

# After bot creation (line ~18):
    bot = Bot(token=settings.telegram_token)
    telegram_queue = TelegramQueue(bot)  # NEW
    dp = Dispatcher()
```

**Step 2: Make queue accessible globally**

```python
# src/codogram/main.py
# Add to module level (before main function):
telegram_queue: TelegramQueue | None = None

# Inside main(), after creating queue:
    global telegram_queue
    telegram_queue = TelegramQueue(bot)
```

**Step 3: Verify syntax**

Run: `python3 -m py_compile src/codogram/main.py`
Expected: No errors

**Step 4: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(main): integrate TelegramQueue"
```

---

## Task 5: Add launch_task field to ThreadInfo

**Files:**
- Modify: `src/codogram/session_manager.py`
- Test: `tests/test_session_manager.py`

**Step 1: Add launch_task field**

Find ThreadInfo dataclass in session_manager.py and add:

```python
@dataclass
class ThreadInfo:
    thread_id: int | None
    name: str
    session_id: str | None = None
    jsonl_path: str | None = None
    last_sent_message: str | None = None
    awaiting_new_session: bool = False
    watcher_task: asyncio.Task | None = None
    poller_task: asyncio.Task | None = None
    binding_task: asyncio.Task | None = None
    launch_task: asyncio.Task | None = None  # NEW
```

**Step 2: Update _to_dict to exclude launch_task**

In ThreadInfo._to_dict(), ensure launch_task is not serialized (it's already not included since only specific fields are serialized).

**Step 3: Verify syntax**

Run: `python3 -m py_compile src/codogram/session_manager.py`
Expected: No errors

**Step 4: Run existing tests**

Run: `pytest tests/test_session_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(session_manager): add launch_task field to ThreadInfo"
```

---

## Task 6: Create launch animation module

**Files:**
- Create: `src/codogram/launch_animation.py`
- Test: `tests/test_launch_animation.py`

**Step 1: Write test for FACES constant**

```python
# tests/test_launch_animation.py
from codogram.launch_animation import FACES, FACE_READY

def test_faces_are_unique():
    """All faces in FACES list are unique."""
    assert len(FACES) == len(set(FACES))

def test_face_ready_not_in_faces():
    """FACE_READY is distinct from animation faces."""
    assert FACE_READY not in FACES
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_launch_animation.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create launch_animation.py**

```python
# src/codogram/launch_animation.py
"""Background launch animation for Claude sessions."""
import asyncio
import time

from aiogram import Bot

from .logging_config import logger
from .session_manager import ProjectState, ThreadInfo
from .telegram_queue import TelegramQueue, EditBatch
from .tmux import TmuxSession, create_tmux_with_claude


FACES = [
    "[._.]",   # Sleeping
    "[-_-]",   # Waking
    "[.o.]",   # Alert
    "[o_o]",   # Watching
    "[◉_◉]",   # Focused
    "[◉︿◉]",  # Tense
    "[°_°]",   # Confused
    "[°□°]",   # Shocked
    "[ಠ_ಠ]",   # Frustrated
    "[ಠ益ಠ]",  # Angry
    "[>_<]",   # Panic
    "[×_×]",   # Overload
    "[☠_☠]",   # Dead
]

FACE_READY = "[≖‿≖]"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_launch_animation.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/launch_animation.py tests/test_launch_animation.py
git commit -m "feat(launch_animation): add faces constants"
```

---

## Task 7: Implement launch_with_animation function

**Files:**
- Modify: `src/codogram/launch_animation.py`

**Step 1: Add launch_with_animation function**

```python
# src/codogram/launch_animation.py (append)

async def launch_with_animation(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
    project: ProjectState,
    thread: ThreadInfo,
    queue: TelegramQueue,
    start_poller,
    start_watcher,
) -> bool:
    """Launch Claude with animated status messages.

    Returns True if successful, False otherwise.
    """
    tmux_name = thread.get_tmux_session(project.project_name)

    try:
        # Block session discovery during startup
        thread.awaiting_new_session = True

        # 1. Status messages
        await bot.send_message(
            chat_id, "Создаю tmux сессию...",
            message_thread_id=thread_id
        )

        result = create_tmux_with_claude(tmux_name, project.cwd)
        if not result.success:
            await bot.send_message(
                chat_id, f"❌ Ошибка: {result.error}",
                message_thread_id=thread_id
            )
            return False

        await bot.send_message(
            chat_id, "Запускаю Claude...",
            message_thread_id=thread_id
        )

        await bot.send_message(
            chat_id, "Жду готовность Claude...",
            message_thread_id=thread_id
        )

        # 2. Wait for ready, animate if > 3 sec
        tmux = TmuxSession(tmux_name, project.cwd)
        start_time = time.time()
        face_msg = None
        face_idx = 0

        while not tmux.is_claude_ready():
            elapsed = time.time() - start_time

            if elapsed > 3 and face_msg is None:
                # First face
                face_msg = await bot.send_message(
                    chat_id, f"`{FACES[0]}`",
                    parse_mode="Markdown",
                    message_thread_id=thread_id
                )
                face_idx = 1

            elif face_msg and face_idx < len(FACES):
                # Next face through queue
                await queue.enqueue(EditBatch(
                    chat_id=chat_id,
                    message_id=face_msg.message_id,
                    text=f"`{FACES[face_idx]}`",
                    parse_mode="Markdown",
                ))
                face_idx += 1

            await asyncio.sleep(3)

            if elapsed > 120:  # Timeout 2 min
                break

        # 3. Finish
        if face_msg:
            await queue.enqueue(EditBatch(
                chat_id=chat_id,
                message_id=face_msg.message_id,
                text=f"`{FACE_READY}`",
                parse_mode="Markdown",
            ))
            await asyncio.sleep(1.5)
            try:
                await bot.delete_message(chat_id, face_msg.message_id)
            except Exception:
                pass

        await bot.send_message(
            chat_id, "✓ Claude готов!",
            message_thread_id=thread_id
        )

        # 4. Start poller/watcher
        # TODO: Integrate with session binding

        return True

    except Exception as e:
        logger.error(f"launch_error: {e}")
        try:
            await bot.send_message(
                chat_id, f"❌ Ошибка запуска: {e}",
                message_thread_id=thread_id
            )
        except Exception:
            pass
        return False

    finally:
        thread.awaiting_new_session = False
        thread.launch_task = None
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/launch_animation.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/launch_animation.py
git commit -m "feat(launch_animation): implement launch_with_animation"
```

---

## Task 8: Update bot.py to use background launch

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Find and update on_start_launch_claude callback**

Find the callback handler for `start:launch_claude` and update it:

```python
@router.callback_query(F.data == "start:launch_claude")
async def on_start_launch_claude(callback: CallbackQuery):
    """Handle launch Claude button click."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state or state.get("state") != "awaiting_launch_confirm":
        await callback.answer("Session expired")
        return

    project = project_manager.get_or_create(state["project"])
    project.cwd = state["path"]
    project.chat_id = chat_id

    # Get or create main thread
    thread = project.get_or_create_thread(None, "main")

    # Check if launch already in progress
    if thread.launch_task and not thread.launch_task.done():
        await callback.answer("⏳ Запуск уже идёт...")
        return

    await callback.answer()
    _start_state.pop(chat_id, None)

    # Import here to avoid circular imports
    from .launch_animation import launch_with_animation
    from .main import telegram_queue

    start_poller, start_watcher = _make_task_starters(callback.bot)

    # Launch in background
    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot,
            chat_id=chat_id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=telegram_queue,
            start_poller=start_poller,
            start_watcher=start_watcher,
        )
    )

    project_manager._save()
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/bot.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): use background launch with animation"
```

---

## Task 9: Update launch_claude_in_thread to use animation

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Replace launch_claude_in_thread body**

Find the `launch_claude_in_thread` function and update to use the new animation:

```python
async def launch_claude_in_thread(
    message: Message,
    project: ProjectState,
    thread: ThreadInfo,
    start_poller,
    start_watcher,
) -> bool:
    """Launch Claude for a specific thread (topic).

    Returns True if successful, False otherwise.
    """
    # Check if launch already in progress
    if thread.launch_task and not thread.launch_task.done():
        await message.answer("⏳ Запуск уже идёт...")
        return False

    from .launch_animation import launch_with_animation
    from .main import telegram_queue

    # Launch in background and wait
    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=thread.thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
            start_poller=start_poller,
            start_watcher=start_watcher,
        )
    )

    # For backwards compatibility, wait for completion
    return await thread.launch_task
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/bot.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): use launch_with_animation in launch_claude_in_thread"
```

---

## Task 10: Run all tests and verify

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 2: Manual test**

1. Start bot: `python -m codogram.main`
2. Send `/start` in Telegram
3. Click "Да, запустить"
4. Verify:
   - Status messages appear sequentially
   - Face animation starts after 3 seconds (if Claude not ready)
   - Other messages can be sent during launch
   - "✓ Claude готов!" appears when ready

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found in manual testing"
```

---

## Task 11: Final cleanup and documentation

**Step 1: Remove old animation code from bot.py**

Delete the old `launch_claude_new` function if it's still there and not being used.

**Step 2: Update any stale comments**

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: cleanup old launch code"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create TelegramQueue dataclasses | telegram_queue.py |
| 2 | Implement TelegramQueue class | telegram_queue.py |
| 3 | Add error handling tests | test_telegram_queue.py |
| 4 | Integrate into main.py | main.py |
| 5 | Add launch_task to ThreadInfo | session_manager.py |
| 6 | Create launch_animation module | launch_animation.py |
| 7 | Implement launch_with_animation | launch_animation.py |
| 8 | Update on_start_launch_claude | bot.py |
| 9 | Update launch_claude_in_thread | bot.py |
| 10 | Run tests and verify | - |
| 11 | Cleanup | - |
