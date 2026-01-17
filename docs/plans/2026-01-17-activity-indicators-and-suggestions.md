# Activity Indicators & Input Suggestions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show Claude's thinking status and input suggestions in Telegram.

**Architecture:** Parse tmux capture-pane for thinking status (spinner lines) and suggestions (input box content). Use TelegramQueue with replace_key for deduplication and edit/delete operations. Thinking status as editable message, suggestions as ReplyKeyboardMarkup attached to Claude's response via SuggestionProvider mediator pattern.

**Tech Stack:** Python 3.12, aiogram 3.x, asyncio, collections.deque

---

## Task 1: Add DeleteBatch to TelegramQueue

**Files:**
- Modify: `src/codogram/telegram_queue.py:34-72`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write the failing test**

```python
# tests/test_telegram_queue.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from codogram.telegram_queue import TelegramQueue, DeleteBatch


@pytest.mark.asyncio
async def test_delete_batch_deletes_message():
    """DeleteBatch should call bot.delete_message."""
    bot = MagicMock()
    bot.delete_message = AsyncMock()

    queue = TelegramQueue(bot)
    batch = DeleteBatch(chat_id=123, message_id=456)

    await queue.enqueue(batch)

    bot.delete_message.assert_called_once_with(123, 456)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_telegram_queue.py::test_delete_batch_deletes_message -v`
Expected: FAIL with "cannot import name 'DeleteBatch'"

**Step 3: Add DeleteBatch dataclass**

In `src/codogram/telegram_queue.py` after `KeyboardBatch` (around line 51):

```python
@dataclass
class DeleteBatch:
    """Delete message operation."""
    chat_id: int
    message_id: int
```

**Step 4: Add _DeleteQueueItem**

After `_KeyboardQueueItem`:

```python
@dataclass
class _DeleteQueueItem:
    """Internal queue item for delete operations."""
    batch: DeleteBatch
    result: asyncio.Future[None] | None
```

**Step 5: Update enqueue() to handle DeleteBatch**

In `enqueue()` method, add handling for DeleteBatch:

```python
async def enqueue(self, batch: OutgoingBatch | EditBatch | KeyboardBatch | DeleteBatch, timeout: float = 120.0) -> list[int] | None:
    # ... existing code ...

    if isinstance(batch, DeleteBatch):
        result_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        item: _QueueItem | _EditQueueItem | _KeyboardQueueItem | _DeleteQueueItem = _DeleteQueueItem(batch=batch, result=result_future)
    elif isinstance(batch, EditBatch):
        # ... existing ...
```

**Step 6: Update enqueue_nowait() similarly**

Add DeleteBatch handling to `enqueue_nowait()`.

**Step 7: Add _delete_message method**

```python
async def _delete_message(self, batch: DeleteBatch) -> None:
    """Delete a message. Silently ignores errors (message already deleted)."""
    try:
        await self.bot.delete_message(batch.chat_id, batch.message_id)
    except Exception as e:
        logger.debug(f"Delete failed (message likely already deleted): {e}")
```

**Step 8: Update _worker to handle DeleteBatch**

In `_worker()`, add:

```python
elif isinstance(item, _DeleteQueueItem):
    await self._delete_message(item.batch)
    if item.result is not None and not item.result.done():
        item.result.set_result(None)
```

**Step 9: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_telegram_queue.py::test_delete_batch_deletes_message -v`
Expected: PASS

**Step 10: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(queue): add DeleteBatch for message deletion"
```

---

## Task 2: Add replace_key and sent_statuses to TelegramQueue

**Files:**
- Modify: `src/codogram/telegram_queue.py`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write the failing test for replace_key deduplication**

```python
@pytest.mark.asyncio
async def test_replace_key_deduplicates_in_queue():
    """Messages with same replace_key should replace each other in queue."""
    bot = MagicMock()
    sent_texts = []

    async def mock_send(*args, **kwargs):
        sent_texts.append(kwargs.get("text"))
        msg = MagicMock()
        msg.message_id = len(sent_texts)
        return msg

    bot.send_message = mock_send

    queue = TelegramQueue(bot)

    # Enqueue 3 messages with same replace_key, only last should be sent
    batch1 = OutgoingBatch(chat_id=123, thread_id=None, messages=[{"text": "first"}], replace_key="status:123")
    batch2 = OutgoingBatch(chat_id=123, thread_id=None, messages=[{"text": "second"}], replace_key="status:123")
    batch3 = OutgoingBatch(chat_id=123, thread_id=None, messages=[{"text": "third"}], replace_key="status:123")

    # Add all without waiting
    await queue.enqueue_nowait(batch1)
    await queue.enqueue_nowait(batch2)
    await queue.enqueue_nowait(batch3)

    # Wait for processing
    await asyncio.sleep(0.5)

    # Only "third" should be sent
    assert sent_texts == ["third"]
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_telegram_queue.py::test_replace_key_deduplicates_in_queue -v`
Expected: FAIL (replace_key not supported yet)

**Step 3: Add replace_key to OutgoingBatch**

```python
@dataclass
class OutgoingBatch:
    """Batch of messages to send atomically."""
    chat_id: int
    thread_id: int | None
    messages: list[dict]  # [{text, parse_mode}, ...]
    reply_markup: InlineKeyboardMarkup | None = None
    replace_key: str | None = None  # If set, replaces previous batch with same key
```

**Step 4: Change queue structure to deque with lock**

In `__init__`:

```python
def __init__(self, bot: Bot):
    self.bot = bot
    self._queues: dict[int, collections.deque] = defaultdict(collections.deque)
    self._queue_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
    self._queue_events: dict[int, asyncio.Event] = defaultdict(asyncio.Event)
    self._workers: dict[int, asyncio.Task] = {}
    self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
    self.sent_statuses: dict[str, int] = {}  # replace_key → msg_id
```

**Step 5: Update enqueue_nowait with replace_key logic**

```python
async def enqueue_nowait(self, batch: OutgoingBatch | EditBatch | KeyboardBatch | DeleteBatch) -> None:
    chat_id = batch.chat_id

    # Create queue item
    if isinstance(batch, DeleteBatch):
        item = _DeleteQueueItem(batch=batch, result=None)
    elif isinstance(batch, EditBatch):
        item = _EditQueueItem(batch=batch, result=None)
    elif isinstance(batch, KeyboardBatch):
        item = _KeyboardQueueItem(batch=batch, result=None)
    else:
        item = _QueueItem(batch=batch, result=None)

    async with self._queue_locks[chat_id]:
        # Replace existing item with same replace_key
        if isinstance(batch, OutgoingBatch) and batch.replace_key:
            queue = self._queues[chat_id]
            for i, existing in enumerate(queue):
                if (isinstance(existing, _QueueItem) and
                    isinstance(existing.batch, OutgoingBatch) and
                    existing.batch.replace_key == batch.replace_key):
                    queue[i] = item
                    self._queue_events[chat_id].set()
                    return

        self._queues[chat_id].append(item)
        self._queue_events[chat_id].set()

    async with self._locks[chat_id]:
        if chat_id not in self._workers or self._workers[chat_id].done():
            self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))
```

**Step 6: Update _worker to use deque**

```python
async def _worker(self, chat_id: int) -> None:
    """Process queue FIFO. Exits after 5 min idle."""
    queue = self._queues[chat_id]
    event = self._queue_events[chat_id]

    while True:
        # Wait for items or timeout
        try:
            await asyncio.wait_for(event.wait(), timeout=300)
        except asyncio.TimeoutError:
            logger.debug(f"Queue worker {chat_id} exiting (idle timeout)")
            return

        # Process all available items
        while True:
            async with self._queue_locks[chat_id]:
                if not queue:
                    event.clear()
                    break
                item = queue.popleft()

            try:
                # ... existing processing logic ...
```

**Step 7: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_telegram_queue.py::test_replace_key_deduplicates_in_queue -v`
Expected: PASS

**Step 8: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(queue): add replace_key for deduplication"
```

---

## Task 3: Add sent_statuses tracking for edit/delete by key

**Files:**
- Modify: `src/codogram/telegram_queue.py`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_sent_statuses_tracks_message_ids():
    """After sending with replace_key, msg_id should be stored in sent_statuses."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))

    queue = TelegramQueue(bot)
    batch = OutgoingBatch(
        chat_id=123,
        thread_id=None,
        messages=[{"text": "test"}],
        replace_key="thinking:123:456"
    )

    await queue.enqueue(batch)

    assert queue.sent_statuses.get("thinking:123:456") == 999
```

**Step 2: Run test to verify it fails**

Expected: FAIL (sent_statuses not populated)

**Step 3: Update _send_batch to store msg_id**

In `_send_batch`, after successful send:

```python
async def _send_batch(self, batch: OutgoingBatch, attempt: int = 0) -> list[int]:
    # ... existing code ...

    # At the end, after return sent_ids:
    if sent_ids and batch.replace_key:
        self.sent_statuses[batch.replace_key] = sent_ids[-1]  # Store last msg_id

    return sent_ids
```

**Step 4: Run test to verify it passes**

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(queue): track sent message IDs by replace_key"
```

---

## Task 4: Add edit/delete by replace_key

**Files:**
- Modify: `src/codogram/telegram_queue.py`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write the failing test for edit by key**

```python
@pytest.mark.asyncio
async def test_edit_by_replace_key():
    """EditBatch with replace_key should use stored msg_id."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    bot.edit_message_text = AsyncMock()

    queue = TelegramQueue(bot)

    # First send
    send_batch = OutgoingBatch(
        chat_id=123, thread_id=None,
        messages=[{"text": "original"}],
        replace_key="status:1"
    )
    await queue.enqueue(send_batch)

    # Then edit by key
    edit_batch = EditBatch(
        chat_id=123, message_id=0,  # 0 = use sent_statuses
        text="updated",
        replace_key="status:1"
    )
    await queue.enqueue(edit_batch)

    bot.edit_message_text.assert_called_with(
        chat_id=123, message_id=999, text="updated",
        parse_mode=None, reply_markup=None
    )
```

**Step 2: Run test to verify it fails**

Expected: FAIL (EditBatch doesn't have replace_key)

**Step 3: Add replace_key to EditBatch**

```python
@dataclass
class EditBatch:
    """Single message edit operation."""
    chat_id: int
    message_id: int  # 0 = lookup from sent_statuses using replace_key
    text: str
    parse_mode: str | None = None
    reply_markup: InlineKeyboardMarkup | None = None
    replace_key: str | None = None  # If message_id=0, use this to lookup
```

**Step 4: Update _edit_message to lookup msg_id**

```python
async def _edit_message(self, batch: EditBatch, attempt: int = 0) -> None:
    # Lookup message_id from sent_statuses if needed
    message_id = batch.message_id
    if message_id == 0 and batch.replace_key:
        message_id = self.sent_statuses.get(batch.replace_key)
        if not message_id:
            logger.debug(f"No stored msg_id for replace_key={batch.replace_key}, skipping edit")
            return

    # ... rest of existing code, using message_id instead of batch.message_id ...
```

**Step 5: Run test to verify it passes**

Expected: PASS

**Step 6: Write test for delete by key**

```python
@pytest.mark.asyncio
async def test_delete_by_replace_key():
    """DeleteBatch with replace_key should use stored msg_id and clean up."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    bot.delete_message = AsyncMock()

    queue = TelegramQueue(bot)

    # First send
    send_batch = OutgoingBatch(
        chat_id=123, thread_id=None,
        messages=[{"text": "temp"}],
        replace_key="status:1"
    )
    await queue.enqueue(send_batch)
    assert queue.sent_statuses.get("status:1") == 999

    # Then delete by key
    delete_batch = DeleteBatch(chat_id=123, message_id=0, replace_key="status:1")
    await queue.enqueue(delete_batch)

    bot.delete_message.assert_called_with(123, 999)
    assert "status:1" not in queue.sent_statuses
```

**Step 7: Add replace_key to DeleteBatch**

```python
@dataclass
class DeleteBatch:
    """Delete message operation."""
    chat_id: int
    message_id: int  # 0 = lookup from sent_statuses using replace_key
    replace_key: str | None = None
```

**Step 8: Update _delete_message**

```python
async def _delete_message(self, batch: DeleteBatch) -> None:
    message_id = batch.message_id
    if message_id == 0 and batch.replace_key:
        message_id = self.sent_statuses.get(batch.replace_key)
        if not message_id:
            logger.debug(f"No stored msg_id for replace_key={batch.replace_key}, skipping delete")
            return

    try:
        await self.bot.delete_message(batch.chat_id, message_id)
    except Exception as e:
        logger.debug(f"Delete failed: {e}")

    # Clean up sent_statuses
    if batch.replace_key and batch.replace_key in self.sent_statuses:
        del self.sent_statuses[batch.replace_key]
```

**Step 9: Run tests**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_telegram_queue.py -v -k "replace_key or delete"`
Expected: All PASS

**Step 10: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(queue): edit and delete by replace_key"
```

---

## Task 5: Add parse_thinking_status to screen.py

**Files:**
- Modify: `src/codogram/screen.py`
- Test: `tests/test_screen.py`

**Step 1: Write the failing test**

```python
# tests/test_screen.py
from codogram.screen import parse_thinking_status


def test_parse_thinking_status_basic():
    """Parse basic thinking status line."""
    output = """
Some previous output
· Wibbling… (ctrl+c to interrupt)
────────────────────────────────────────
❯
────────────────────────────────────────
"""
    result = parse_thinking_status(output)
    assert result == "· Wibbling… (/ctrl_c)"


def test_parse_thinking_status_with_details():
    """Parse thinking status with time and tokens."""
    output = """
✶ Hatching… (ctrl+c to interrupt · 30s · ↓ 914 tokens · thinking)
────────────────────────────────────────
"""
    result = parse_thinking_status(output)
    assert result == "✶ Hatching… (/ctrl_c · 30s · ↓ 914 tokens · thinking)"


def test_parse_thinking_status_esc():
    """Parse with esc instead of ctrl+c."""
    output = "· Thinking… (esc to interrupt · 5s)"
    result = parse_thinking_status(output)
    assert result == "· Thinking… (/esc · 5s)"


def test_parse_thinking_status_cooked():
    """Parse completion status."""
    output = "✻ Cooked for 35s\n────────"
    result = parse_thinking_status(output)
    assert result == "✻ Cooked for 35s"


def test_parse_thinking_status_none():
    """Return None when no thinking status."""
    output = """
────────────────────────────────────────
❯
────────────────────────────────────────
"""
    result = parse_thinking_status(output)
    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_screen.py -v -k "thinking"`
Expected: FAIL with "cannot import name 'parse_thinking_status'"

**Step 3: Implement parse_thinking_status**

Add to `src/codogram/screen.py`:

```python
THINKING_SPINNERS = "·✶✻✽*✢"


def parse_thinking_status(output: str) -> str | None:
    """Parse thinking status line as-is.

    Formats vary:
    - · Wibbling… (ctrl+c to interrupt)
    - ✶ Wibbling… (ctrl+c to interrupt · 30s · ↓ 914 tokens · thinking)
    - ✻ Cooked for 35s

    Returns raw line with command injection:
    - 'esc to interrupt' → '/esc'
    - 'ctrl+c to interrupt' → '/ctrl_c'
    """
    for line in output.split("\n"):
        stripped = line.strip()
        if stripped and stripped[0] in THINKING_SPINNERS:
            result = stripped.replace("esc to interrupt", "/esc")
            result = result.replace("ctrl+c to interrupt", "/ctrl_c")
            return result
    return None
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_screen.py -v -k "thinking"`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py
git commit -m "feat(screen): add parse_thinking_status"
```

---

## Task 6: Add parse_input_suggestion to screen.py

**Files:**
- Modify: `src/codogram/screen.py`
- Test: `tests/test_screen.py`

**Step 1: Write the failing test**

```python
def test_parse_input_suggestion_basic():
    """Parse suggestion from input box."""
    output = """
● Response text
────────────────────────────────────────
❯ посмотри что залогировалось                                            ↵ send
────────────────────────────────────────
"""
    result = parse_input_suggestion(output)
    assert result == "посмотри что залогировалось"


def test_parse_input_suggestion_empty():
    """Return None for empty input."""
    output = """
────────────────────────────────────────
❯
────────────────────────────────────────
"""
    result = parse_input_suggestion(output)
    assert result is None


def test_parse_input_suggestion_user_typing():
    """Return None when user is typing (no ↵ send)."""
    output = """
────────────────────────────────────────
❯ my custom text
────────────────────────────────────────
"""
    result = parse_input_suggestion(output)
    assert result is None
```

**Step 2: Run tests to verify they fail**

Expected: FAIL with "cannot import name 'parse_input_suggestion'"

**Step 3: Implement parse_input_suggestion**

```python
import re


def parse_input_suggestion(output: str) -> str | None:
    """Parse suggestion from input box.

    Format: ❯ suggestion text                    ↵ send
    Located between last two ──── lines (input box).

    Returns suggestion text or None if no suggestion.
    """
    lines = output.split("\n")

    # Find last two ──── separators
    sep_indices = []
    for i, line in enumerate(lines):
        if "─" * 10 in line:
            sep_indices.append(i)

    if len(sep_indices) < 2:
        return None

    # Get content between last two separators
    start = sep_indices[-2]
    end = sep_indices[-1]

    content = "\n".join(lines[start + 1:end]).strip()

    # Match pattern: ❯ text ↵ send
    # \xa0 is non-breaking space that Claude uses
    match = re.match(r'❯[\s\xa0]*(.+?)[\s\xa0]*↵\s*send', content)
    if match:
        suggestion = match.group(1).strip()
        if suggestion:
            return suggestion

    return None
```

**Step 4: Run tests to verify they pass**

Expected: All PASS

**Step 5: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py
git commit -m "feat(screen): add parse_input_suggestion"
```

---

## Task 7: Add thinking status handling to permission_poller

**Files:**
- Modify: `src/codogram/permission_poller.py`
- Test: Manual E2E

**Step 1: Import new functions**

Add to imports in `permission_poller.py`:

```python
from .screen import parse_screen, PermissionPrompt, is_claude_ready, parse_thinking_status
from .telegram_queue import OutgoingBatch, EditBatch, DeleteBatch
```

**Step 2: Add state variables**

In `permission_poller()` function, after existing state variables:

```python
# Thinking status state
thinking_msg_key: str | None = None
last_thinking_update: float = 0.0
last_thinking_text: str | None = None
```

**Step 3: Add thinking status logic in main loop**

After `parsed = parse_screen(screen)`, add:

```python
# Parse thinking status
thinking_text = parse_thinking_status(screen)

if thinking_text:
    now = asyncio.get_event_loop().time()
    # Throttle updates to every 3 seconds, but always send if text changed
    if thinking_text != last_thinking_text or now - last_thinking_update >= 3.0:
        key = f"thinking:{project.chat_id}:{thread_id}"

        if thinking_msg_key is None:
            # First time — send
            batch = OutgoingBatch(
                chat_id=project.chat_id,
                thread_id=thread_id,
                messages=[{"text": thinking_text}],
                replace_key=key,
            )
            thinking_msg_key = key
        else:
            # Update — edit
            batch = EditBatch(
                chat_id=project.chat_id,
                message_id=0,  # Lookup from sent_statuses
                text=thinking_text,
                replace_key=key,
            )

        await telegram_queue.enqueue_nowait(batch)
        last_thinking_update = now
        last_thinking_text = thinking_text

elif thinking_msg_key:
    # Claude finished — delete
    batch = DeleteBatch(
        chat_id=project.chat_id,
        message_id=0,
        replace_key=thinking_msg_key,
    )
    await telegram_queue.enqueue_nowait(batch)
    thinking_msg_key = None
    last_thinking_text = None
```

**Step 4: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "feat(poller): add thinking status display"
```

---

## Task 8: Add /ctrl_c command

**Files:**
- Create: `src/codogram/handlers/ctrl_c.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create handler file**

```python
# src/codogram/handlers/ctrl_c.py
"""Ctrl+C command handler - interrupt Claude."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from ..tmux import TmuxSession

router = Router(name="ctrl_c")


def _get_tmux_for_context(chat_id: int, thread_id: int | None) -> TmuxSession | None:
    """Get TmuxSession for current chat/thread context."""
    project = project_manager.get_by_chat(chat_id)
    if not project:
        return None

    if project.threads:
        thread = project.threads.get(thread_id)
        if thread:
            tmux_name = thread.get_tmux_session(project.project_name)
            return TmuxSession(tmux_name, thread.worktree_path or project.cwd)

    if project.tmux_session:
        return TmuxSession(project.tmux_session, project.cwd)

    return None


@router.message(Command("ctrl_c"))
async def cmd_ctrl_c(message: Message, telegram_queue: TelegramQueue):
    """Send Ctrl+C to interrupt Claude."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    tmux = _get_tmux_for_context(chat_id, thread_id)
    if not tmux:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    try:
        tmux.send_key("C-c")
        await telegram_queue.reply(message, "`Ctrl+C` sent", parse_mode="MarkdownV2")
    except Exception as e:
        await telegram_queue.reply(message, f"Error: {e}")
```

**Step 2: Register router**

In `src/codogram/handlers/__init__.py`, add:

```python
from .ctrl_c import router as ctrl_c_router
# ...
def register_handlers(dp: Dispatcher) -> None:
    # ... existing routers ...
    dp.include_router(ctrl_c_router)
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/ctrl_c.py src/codogram/handlers/__init__.py
git commit -m "feat: add /ctrl_c command to interrupt Claude"
```

---

## Task 9: Create SuggestionProvider mediator class

**Files:**
- Create: `src/codogram/suggestion_provider.py`
- Test: `tests/test_suggestion_provider.py`

**Step 1: Write the failing test**

```python
# tests/test_suggestion_provider.py
import pytest
import asyncio
from codogram.suggestion_provider import SuggestionProvider


@pytest.mark.asyncio
async def test_set_and_get_suggestion():
    """Provider should store and return suggestion."""
    provider = SuggestionProvider()

    provider.set_suggestion(123, 456, "run the tests")
    result = await provider.wait_for_suggestion(123, 456, timeout=0.1)

    assert result == "run the tests"


@pytest.mark.asyncio
async def test_get_suggestion_clears_it():
    """Getting suggestion should clear it (one-time use)."""
    provider = SuggestionProvider()

    provider.set_suggestion(123, 456, "run the tests")
    await provider.wait_for_suggestion(123, 456, timeout=0.1)
    result = await provider.wait_for_suggestion(123, 456, timeout=0.1)

    assert result is None


@pytest.mark.asyncio
async def test_wait_for_suggestion_returns_none_on_timeout():
    """Should return None if no suggestion within timeout."""
    provider = SuggestionProvider()

    result = await provider.wait_for_suggestion(123, 456, timeout=0.1)

    assert result is None


@pytest.mark.asyncio
async def test_wait_unblocks_when_suggestion_set():
    """Waiting should unblock when suggestion is set."""
    provider = SuggestionProvider()

    async def set_later():
        await asyncio.sleep(0.05)
        provider.set_suggestion(123, 456, "late suggestion")

    asyncio.create_task(set_later())
    result = await provider.wait_for_suggestion(123, 456, timeout=1.0)

    assert result == "late suggestion"


@pytest.mark.asyncio
async def test_clear_suggestion():
    """Setting None should clear suggestion."""
    provider = SuggestionProvider()

    provider.set_suggestion(123, 456, "test")
    provider.set_suggestion(123, 456, None)
    result = await provider.wait_for_suggestion(123, 456, timeout=0.1)

    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_suggestion_provider.py -v`
Expected: FAIL with "No module named 'codogram.suggestion_provider'"

**Step 3: Implement SuggestionProvider**

```python
# src/codogram/suggestion_provider.py
"""SuggestionProvider - mediator between Poller (producer) and Watcher (consumer)."""
import asyncio


class SuggestionProvider:
    """Bridge between Poller (producer) and Watcher (consumer).

    Poller calls set_suggestion() when it detects a suggestion in tmux.
    Watcher calls wait_for_suggestion() before sending Claude's response.
    """

    def __init__(self):
        self._suggestions: dict[str, str] = {}  # key → suggestion
        self._events: dict[str, asyncio.Event] = {}

    def _key(self, chat_id: int, thread_id: int | None) -> str:
        return f"{chat_id}:{thread_id}"

    def set_suggestion(self, chat_id: int, thread_id: int | None, suggestion: str | None) -> None:
        """Called by Poller when suggestion found/cleared."""
        key = self._key(chat_id, thread_id)
        if suggestion:
            self._suggestions[key] = suggestion
            # Wake up any waiting consumer
            if key in self._events:
                self._events[key].set()
        else:
            self._suggestions.pop(key, None)

    async def wait_for_suggestion(
        self, chat_id: int, thread_id: int | None, timeout: float = 1.0
    ) -> str | None:
        """Called by Watcher before sending response.

        Waits up to `timeout` seconds for a suggestion to appear.
        Returns suggestion (and clears it) or None if timeout.
        """
        key = self._key(chat_id, thread_id)

        # If suggestion already available, return immediately
        if key in self._suggestions:
            return self._suggestions.pop(key)

        # Wait for suggestion to be set
        event = self._events.setdefault(key, asyncio.Event())
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout)
            return self._suggestions.pop(key, None)
        except asyncio.TimeoutError:
            return None


# Global singleton
suggestion_provider = SuggestionProvider()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/superbereza/dev/codogram && ./venv/bin/pytest tests/test_suggestion_provider.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/codogram/suggestion_provider.py tests/test_suggestion_provider.py
git commit -m "feat: add SuggestionProvider mediator class"
```

---

## Task 9b: Add suggestion detection to permission_poller

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Import suggestion_provider and parse function**

```python
from .suggestion_provider import suggestion_provider
from .screen import parse_input_suggestion
```

**Step 2: Add suggestion detection in main loop**

After thinking status logic, add:

```python
# Parse input suggestion (only when not thinking)
if not thinking_text:
    suggestion = parse_input_suggestion(screen)
    # Set suggestion in provider (watcher will pick it up)
    suggestion_provider.set_suggestion(project.chat_id, thread_id, suggestion)
```

**Step 3: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "feat(poller): detect suggestions and publish to SuggestionProvider"
```

---

## Task 10: Integrate SuggestionProvider into Watcher

**Files:**
- Modify: `src/codogram/watcher.py`

**Step 1: Import SuggestionProvider**

```python
from .suggestion_provider import suggestion_provider
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
```

**Step 2: Find where response is sent to Telegram**

Locate the code in watcher that sends Claude's response to Telegram (likely via OutgoingBatch).

**Step 3: Add suggestion waiting before sending response**

Before sending the response batch, wait for suggestion:

```python
# Wait briefly for suggestion from poller
suggestion = await suggestion_provider.wait_for_suggestion(
    chat_id=project.chat_id,
    thread_id=thread_id,
    timeout=1.0  # Wait up to 1 second
)

# Attach ReplyKeyboard if suggestion found
reply_markup = None
if suggestion:
    reply_markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=suggestion)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

batch = OutgoingBatch(
    chat_id=project.chat_id,
    thread_id=thread_id,
    messages=[{"text": response_text}],
    reply_markup=reply_markup,  # Attached to response message
)
await telegram_queue.enqueue(batch)
```

**Step 4: Commit**

```bash
git add src/codogram/watcher.py
git commit -m "feat(watcher): attach suggestion keyboard to Claude's response"
```

---

## Task 11: E2E Testing

**Step 1: Test thinking status**

1. Start bot: `cd /home/superbereza/dev/codogram/.worktrees/show-thinking-status && ./dev-run.sh`
2. Send message to Claude in Telegram
3. Verify: thinking status message appears with spinner (e.g., "· Thinking… (/ctrl_c)")
4. Verify: message updates every ~3 sec with new time/tokens
5. Verify: message deleted when Claude responds

**Step 2: Test /ctrl_c**

1. Send long task to Claude
2. While Claude is thinking, send `/ctrl_c`
3. Verify: Claude is interrupted

**Step 3: Test input suggestions**

1. Send message that will trigger a suggestion (e.g., ask Claude to run tests)
2. Wait for Claude response
3. Verify: ReplyKeyboard appears ATTACHED to the response message (not separate)
4. Click suggestion button
5. Verify: text sent to Claude
6. Verify: keyboard disappears (one_time_keyboard behavior)

**Step 4: Test suggestion timing**

1. Verify suggestion appears even if there's a small delay between response and suggestion detection
2. Verify that if no suggestion found within 1 second, response is sent without keyboard

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat: activity indicators and input suggestions complete"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add DeleteBatch | telegram_queue.py |
| 2 | Add replace_key deduplication | telegram_queue.py |
| 3 | Add sent_statuses tracking | telegram_queue.py |
| 4 | Edit/delete by replace_key | telegram_queue.py |
| 5 | parse_thinking_status | screen.py |
| 6 | parse_input_suggestion | screen.py |
| 7 | Thinking status in poller | permission_poller.py |
| 8 | /ctrl_c command | handlers/ctrl_c.py |
| 9 | SuggestionProvider mediator | suggestion_provider.py |
| 9b | Suggestion detection in poller | permission_poller.py |
| 10 | Suggestion keyboard in watcher | watcher.py |
| 11 | E2E testing | manual |
