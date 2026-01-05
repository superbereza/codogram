# Unified Message Queue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Route all outgoing Telegram messages through TelegramQueue with convenient helpers.

**Architecture:** Add `reply()`, `send()`, `edit()` helpers to TelegramQueue. Use aiogram native DI to inject queue into handlers. Migrate ~89 direct calls to use helpers.

**Tech Stack:** aiogram 3.x DI, asyncio, TelegramQueue

**Design doc:** `docs/designs/2025-01-04-unified-message-queue.md`

---

### Task 1: Add TelegramQueueTimeout exception

**Files:**
- Modify: `src/codogram/telegram_queue.py:1-15`

**Step 1: Add exception class**

```python
# After imports, before dataclasses
class TelegramQueueTimeout(Exception):
    """Raised when queue operation times out."""
    pass
```

**Step 2: Run tests**

Run: `PYTHONPATH=src pytest tests/test_telegram_queue.py -v`
Expected: PASS (no behavior change yet)

**Step 3: Commit**

```bash
git add src/codogram/telegram_queue.py
git commit -m "feat(queue): add TelegramQueueTimeout exception"
```

---

### Task 2: Add timeout to enqueue()

**Files:**
- Modify: `src/codogram/telegram_queue.py:75-106`
- Test: `tests/test_telegram_queue.py`

**Step 1: Write failing test**

```python
# tests/test_telegram_queue.py
import asyncio
import pytest
from codogram.telegram_queue import TelegramQueue, TelegramQueueTimeout, OutgoingBatch

@pytest.mark.asyncio
async def test_enqueue_timeout():
    """Test that enqueue raises timeout after specified duration."""
    from unittest.mock import MagicMock

    bot = MagicMock()
    # Make send_message hang forever
    async def hang_forever(**kw):
        await asyncio.sleep(100)
    bot.send_message = hang_forever

    queue = TelegramQueue(bot)
    batch = OutgoingBatch(chat_id=123, thread_id=None, messages=[{"text": "test"}])

    with pytest.raises(TelegramQueueTimeout):
        await queue.enqueue(batch, timeout=0.1)

    await queue.shutdown()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_telegram_queue.py::test_enqueue_timeout -v`
Expected: FAIL (timeout parameter doesn't exist)

**Step 3: Implement timeout parameter**

```python
async def enqueue(
    self,
    batch: OutgoingBatch | EditBatch | KeyboardBatch,
    timeout: float = 30.0,
) -> list[int] | None:
    """Add batch to queue, wait for send.

    Args:
        batch: The batch to send
        timeout: Max seconds to wait (default 30s)

    Raises:
        TelegramQueueTimeout: If operation exceeds timeout
    """
    chat_id = batch.chat_id

    # ... existing item creation code ...

    await self._queues[chat_id].put(item)

    try:
        if isinstance(batch, EditBatch):
            await asyncio.wait_for(result_future, timeout)
            return None
        elif isinstance(batch, KeyboardBatch):
            return await asyncio.wait_for(result_future_kb, timeout)
        else:
            return await asyncio.wait_for(result_future_send, timeout)
    except asyncio.TimeoutError:
        raise TelegramQueueTimeout(f"Queue timeout for chat {chat_id}")
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_telegram_queue.py::test_enqueue_timeout -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(queue): add timeout parameter to enqueue()"
```

---

### Task 3: Add reply_markup to EditBatch

**Files:**
- Modify: `src/codogram/telegram_queue.py:24-31` (EditBatch dataclass)
- Modify: `src/codogram/telegram_queue.py:237-276` (_edit_message method)

**Step 1: Update EditBatch dataclass**

```python
@dataclass
class EditBatch:
    """Single message edit operation."""
    chat_id: int
    message_id: int
    text: str
    parse_mode: str | None = None
    reply_markup: InlineKeyboardMarkup | None = None  # NEW
```

**Step 2: Update _edit_message to use reply_markup AND telegramify**

Currently `_edit_message()` does NOT call telegramify, but `_send_batch()` does. Fix this inconsistency:

```python
async def _edit_message(self, batch: EditBatch, attempt: int = 0) -> None:
    """Edit a message. Handles rate limits and parse errors."""
    MAX_ATTEMPTS = 3

    if attempt >= MAX_ATTEMPTS:
        logger.error(
            f"Edit failed after {MAX_ATTEMPTS} attempts, "
            f"chat_id={batch.chat_id}, message_id={batch.message_id}"
        )
        return

    # NEW: Apply telegramify for MarkdownV2
    text = batch.text
    if batch.parse_mode == "MarkdownV2":
        try:
            text = telegramify_markdown.markdownify(
                text,
                max_line_length=None,
                normalize_whitespace=False
            )
        except Exception as e:
            logger.warning(f"markdownify failed on edit: {e}")

    try:
        await self.bot.edit_message_text(
            chat_id=batch.chat_id,
            message_id=batch.message_id,
            text=text,  # Use processed text
            parse_mode=batch.parse_mode,
            reply_markup=batch.reply_markup,  # NEW
        )
    # ... rest of exception handling stays the same ...
```

**Step 3: Run tests**

Run: `PYTHONPATH=src pytest tests/test_telegram_queue.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/codogram/telegram_queue.py
git commit -m "feat(queue): add reply_markup to EditBatch"
```

---

### Task 4: Add helper methods to TelegramQueue

**Files:**
- Modify: `src/codogram/telegram_queue.py` (add methods at end of class)
- Test: `tests/test_telegram_queue.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_reply_helper():
    """Test reply() helper creates correct batch."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from aiogram.types import Message, Chat

    bot = MagicMock()
    queue = TelegramQueue(bot)

    # Mock message
    message = MagicMock(spec=Message)
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 123
    message.message_thread_id = 456

    with patch.object(queue, 'enqueue', new_callable=AsyncMock) as mock_enqueue:
        mock_enqueue.return_value = [789]
        result = await queue.reply(message, "Hello")

        assert result == [789]
        mock_enqueue.assert_called_once()
        batch = mock_enqueue.call_args[0][0]
        assert batch.chat_id == 123
        assert batch.thread_id == 456
        assert batch.messages[0]["text"] == "Hello"
        assert batch.messages[0]["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_send_helper():
    """Test send() helper creates correct batch."""
    from unittest.mock import AsyncMock, MagicMock, patch

    bot = MagicMock()
    queue = TelegramQueue(bot)

    with patch.object(queue, 'enqueue', new_callable=AsyncMock) as mock_enqueue:
        mock_enqueue.return_value = [789]
        result = await queue.send(123, "Hello", thread_id=456)

        assert result == [789]
        batch = mock_enqueue.call_args[0][0]
        assert batch.chat_id == 123
        assert batch.thread_id == 456


@pytest.mark.asyncio
async def test_edit_helper():
    """Test edit() helper creates correct batch."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from aiogram.types import Message, Chat

    bot = MagicMock()
    queue = TelegramQueue(bot)

    message = MagicMock(spec=Message)
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 123
    message.message_id = 456

    with patch.object(queue, 'enqueue', new_callable=AsyncMock) as mock_enqueue:
        mock_enqueue.return_value = None
        await queue.edit(message, "Updated")

        batch = mock_enqueue.call_args[0][0]
        assert batch.chat_id == 123
        assert batch.message_id == 456
        assert batch.text == "Updated"
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/test_telegram_queue.py::test_reply_helper -v`
Expected: FAIL (method doesn't exist)

**Step 3: Implement helper methods**

```python
# Add to TelegramQueue class, after shutdown()

async def reply(
    self,
    message: "Message",
    text: str,
    parse_mode: str | None = "MarkdownV2",
    reply_markup: "InlineKeyboardMarkup | None" = None,
) -> list[int]:
    """Reply to a message through queue.

    Args:
        message: The message to reply to
        text: Text content
        parse_mode: Parse mode (default MarkdownV2, None to skip telegramify)
        reply_markup: Optional inline keyboard

    Returns:
        List of sent message IDs
    """
    msg_dict: dict = {"text": text}
    if parse_mode:
        msg_dict["parse_mode"] = parse_mode
    if reply_markup:
        msg_dict["reply_markup"] = reply_markup

    batch = OutgoingBatch(
        chat_id=message.chat.id,
        thread_id=message.message_thread_id,
        messages=[msg_dict],
    )
    return await self.enqueue(batch)

async def send(
    self,
    chat_id: int,
    text: str,
    thread_id: int | None = None,
    parse_mode: str | None = "MarkdownV2",
    reply_markup: "InlineKeyboardMarkup | None" = None,
) -> list[int]:
    """Send message to chat through queue.

    Args:
        chat_id: Target chat ID
        text: Text content
        thread_id: Optional thread/topic ID
        parse_mode: Parse mode (default MarkdownV2, None to skip telegramify)
        reply_markup: Optional inline keyboard

    Returns:
        List of sent message IDs
    """
    msg_dict: dict = {"text": text}
    if parse_mode:
        msg_dict["parse_mode"] = parse_mode
    if reply_markup:
        msg_dict["reply_markup"] = reply_markup

    batch = OutgoingBatch(
        chat_id=chat_id,
        thread_id=thread_id,
        messages=[msg_dict],
    )
    return await self.enqueue(batch)

async def edit(
    self,
    message: "Message",
    text: str,
    parse_mode: str | None = "MarkdownV2",
    reply_markup: "InlineKeyboardMarkup | None" = None,
) -> None:
    """Edit a message through queue.

    Args:
        message: The message to edit
        text: New text content
        parse_mode: Parse mode (default MarkdownV2, None to skip telegramify)
        reply_markup: Optional inline keyboard
    """
    batch = EditBatch(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
    await self.enqueue(batch)
```

**Step 4: Add Message import**

```python
# At top of file, update TYPE_CHECKING imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from aiogram.types import Message
```

**Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_telegram_queue.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/telegram_queue.py tests/test_telegram_queue.py
git commit -m "feat(queue): add reply(), send(), edit() helpers"
```

---

### Task 5: Register queue on Dispatcher for DI

**Files:**
- Modify: `src/codogram/main.py:31-32`

**Step 1: Register queue on dispatcher**

```python
# After creating queue and dispatcher
bot = Bot(token=settings.telegram_token)
global telegram_queue
telegram_queue = TelegramQueue(bot)
dp = Dispatcher()
dp["telegram_queue"] = telegram_queue  # NEW - register for DI
```

**Step 2: Run bot to verify no errors**

Run: `PYTHONPATH=src python -c "from codogram.main import main; print('OK')"`
Expected: OK (no import errors)

**Step 3: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(main): register telegram_queue for aiogram DI"
```

---

### Task 6: Migrate common.py + threads.py + branches.py (together)

**Files:**
- Modify: `src/codogram/handlers/common.py`
- Modify: `src/codogram/handlers/threads.py`
- Modify: `src/codogram/handlers/branches.py`

**Why together:** `require_forum_group()` is called by threads.py and branches.py. Changing signature requires updating all callers in same commit.

**Step 1: Update require_forum_group in common.py**

```python
from ..telegram_queue import TelegramQueue

async def require_forum_group(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await telegram_queue.reply(message, "`[!]` This command requires a group with topics.")
        return False
    if not message.chat.is_forum:
        await telegram_queue.reply(message, "`[!]` Topics required. Enable in group settings -> Topics")
        return False
    return True
```

**Step 2: Update cb_cancel in common.py**

```python
@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    _flow_state.pop(chat_id, None)
    await telegram_queue.edit(callback.message, "Cancelled.")
    await callback.answer()
```

**Step 3: Update threads.py**

Add `telegram_queue: TelegramQueue` parameter to all handlers.
Update `require_forum_group(message)` → `require_forum_group(message, telegram_queue)`.
Replace all `message.answer()` → `telegram_queue.reply()`.
Replace `bot.send_message()` → `telegram_queue.send()`.

**Step 4: Update branches.py**

Same pattern as threads.py.

**Step 5: Run tests**

Run: `PYTHONPATH=src pytest tests/ -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/handlers/common.py src/codogram/handlers/threads.py src/codogram/handlers/branches.py
git commit -m "refactor(handlers): migrate common, threads, branches to telegram_queue"
```

---

### Task 7: Migrate handlers/messages.py

**Files:**
- Modify: `src/codogram/handlers/messages.py`

**Step 1: Add telegram_queue parameter to handlers**

Update each handler that uses `message.answer()` to:
1. Add `telegram_queue: TelegramQueue` parameter
2. Replace `await message.answer(...)` with `await telegram_queue.reply(message, ...)`

**Step 2: Run tests**

Run: `PYTHONPATH=src pytest tests/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/codogram/handlers/messages.py
git commit -m "refactor(handlers): migrate messages.py to telegram_queue"
```

---

### Task 8: Migrate handlers/settings.py

**Files:**
- Modify: `src/codogram/handlers/settings.py`

Same pattern as Task 7.

**Commit:**
```bash
git commit -m "refactor(handlers): migrate settings.py to telegram_queue"
```

---

### Task 9: Migrate handlers/sessions.py

**Files:**
- Modify: `src/codogram/handlers/sessions.py`

Same pattern as Task 7.

**Commit:**
```bash
git commit -m "refactor(handlers): migrate sessions.py to telegram_queue"
```


---

### Task 10: Migrate handlers/start.py

**Files:**
- Modify: `src/codogram/handlers/start.py`

Largest file - 18 answer() + ~10 edit_text().

**Commit:**
```bash
git commit -m "refactor(handlers): migrate start.py to telegram_queue"
```

---

### Task 11: Migrate services/launch.py

**Files:**
- Modify: `src/codogram/services/launch.py`

Has 3 `bot.send_message()` calls.

**Commit:**
```bash
git commit -m "refactor(services): migrate launch.py to telegram_queue"
```

---

### Task 12: Migrate launch_animation.py

**Files:**
- Modify: `src/codogram/launch_animation.py`

Has 8 `bot.send_message()` + 1 edit.

**Commit:**
```bash
git commit -m "refactor: migrate launch_animation.py to telegram_queue"
```

---

### Task 13: Migrate adapters/telegram.py

**Files:**
- Modify: `src/codogram/adapters/telegram.py`

Has 1 `bot.send_message()` call.

**Commit:**
```bash
git commit -m "refactor(adapters): migrate telegram.py to telegram_queue"
```

---

### Task 14: Migrate middleware/admin.py

**Files:**
- Modify: `src/codogram/middleware/admin.py`

**Note:** In middleware, DI values are in `data` dict, not as function parameters.

**Step 1: Update middleware to use queue from data**

```python
async def __call__(self, handler, event, data):
    telegram_queue = data.get("telegram_queue")  # Get from DI
    user: User | None = data.get("event_from_user")

    if user is None:
        return None

    if is_admin(user.id):
        return await handler(event, data)

    await self._reject_non_admin(event, user.id, telegram_queue)
    return None

async def _reject_non_admin(self, event, user_id, telegram_queue):
    if telegram_queue and hasattr(event, 'chat'):  # Message
        await telegram_queue.send(
            event.chat.id,
            f"`\\[x\\]` Not admin\\. Your ID: `{user_id}`\n"
            f"Add to ADMIN\\_IDS in \\.env",
        )
    elif hasattr(event, 'answer'):  # CallbackQuery - toast, keep direct
        await event.answer(f"[x] Not admin. Your ID: {user_id}", show_alert=True)
```

**Step 2: Run tests**

Run: `PYTHONPATH=src pytest tests/test_admin_middleware.py -v`

**Step 3: Commit**

```bash
git commit -m "refactor(middleware): migrate admin.py to telegram_queue"
```

---

### Task 15: Final verification

**Step 1: Run all tests**

Run: `PYTHONPATH=src pytest tests/ -v`
Expected: All PASS

**Step 2: Grep for remaining direct calls**

Run: `grep -r "\.answer\(" src/codogram/handlers/ | grep -v "callback.answer"`
Expected: No results (all migrated)

Run: `grep -r "bot\.send_message" src/codogram/ | grep -v telegram_queue.py`
Expected: No results (all migrated)

**Step 3: Manual E2E test**

1. Start bot: `./restart.sh`
2. Send `/start` in Telegram
3. Verify messages appear correctly
4. Test permission prompt (Yes/No buttons)

**Step 4: Commit**

```bash
git commit -m "docs: unified message queue migration complete"
```
