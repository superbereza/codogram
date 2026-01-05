# Unified Message Queue

**Date:** 2025-01-04
**Status:** Draft (reviewed)

## Problem

Messages are sent through two paths:
1. **TelegramQueue** - Claude output, notifications (has rate limiting, retry, telegramify)
2. **Direct calls** - handlers use `message.answer()`, `bot.send_message()` (no rate limiting)

This causes:
- Inconsistent rate limiting (handlers can trigger flood)
- telegramify only works for queue messages
- Duplicate error handling logic
- Hard to add cross-cutting concerns (logging, metrics)

## Solution

Route ALL outgoing messages through TelegramQueue with convenient helpers.

### New Helper Methods

```python
class TelegramQueue:
    async def reply(
        self,
        message: Message,
        text: str,
        parse_mode: str | None = "MarkdownV2",
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> list[int]:
        """Reply to a message through queue."""

    async def send(
        self,
        chat_id: int,
        text: str,
        thread_id: int | None = None,
        parse_mode: str | None = "MarkdownV2",
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> list[int]:
        """Send message to chat through queue."""

    async def edit(
        self,
        message: Message,
        text: str,
        parse_mode: str | None = "MarkdownV2",
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """Edit a message through queue."""
```

### Usage Change

Before:
```python
await message.answer("Hello", parse_mode="MarkdownV2")
await bot.send_message(chat_id, "Hello", parse_mode="MarkdownV2")
await callback.message.edit_text("Updated", reply_markup=keyboard)
```

After:
```python
await telegram_queue.reply(message, "Hello")
await telegram_queue.send(chat_id, "Hello", thread_id=thread_id)
await telegram_queue.edit(callback.message, "Updated", reply_markup=keyboard)
```

### What NOT to Change

- `callback.answer()` - toast/popup, not a chat message
- `telegram_queue.py` internal `bot.send_message()` - already in queue

## Scope

### Files to Modify

| File | `answer()` | `send_message()` | `edit_text()` | Total |
|------|-----------|------------------|---------------|-------|
| handlers/start.py | 18 | 0 | ~10 | 28 |
| handlers/branches.py | 10 | 0 | ~8 | 18 |
| handlers/threads.py | 7 | 1 | ~3 | 11 |
| handlers/settings.py | 7 | 0 | 0 | 7 |
| handlers/sessions.py | 5 | 0 | 0 | 5 |
| handlers/messages.py | 3 | 0 | 0 | 3 |
| handlers/common.py | 2 | 0 | 1 | 3 |
| services/launch.py | 0 | 3 | 0 | 3 |
| launch_animation.py | 0 | 8 | 1 | 9 |
| adapters/telegram.py | 0 | 1 | 0 | 1 |
| middleware/admin.py | 1 | 0 | 0 | 1 |
| **Total** | **53** | **13** | **~23** | **~89** |

### Out of Scope

- Media messages (photos, documents) - text only for now
- `callback.answer()` calls (~30) - toasts, not messages

## Design Decisions

### 1. Queue Access in Handlers

**Decision: aiogram native Dependency Injection**

aiogram 3.x has built-in DI. Register queue on Dispatcher, handlers receive it as parameter:

```python
# main.py - register for DI
dp = Dispatcher()
dp["telegram_queue"] = telegram_queue

# handlers - automatically injected
@router.message(Command("start"))
async def cmd_start(message: Message, telegram_queue: TelegramQueue):
    await telegram_queue.reply(message, "Hello")
```

This is the standard aiogram pattern (same as `state: FSMContext`).

**Why not middleware injection (`message.bot["telegram_queue"]`)?**
- Not standard aiogram practice
- `bot["key"]` is for bot-level config, not request dependencies
- Harder to test

### 2. Default parse_mode

Default to `"MarkdownV2"` - all messages go through telegramify for consistent formatting.

Pass `parse_mode=None` to skip telegramify (for controlled static text).

### 3. Fire-and-forget vs Wait

- `reply()` / `send()` / `edit()` - wait for completion (default)
- `reply_nowait()` / `send_nowait()` - fire-and-forget for notifications

### 4. Timeout Protection

Add timeout to `enqueue()` to prevent handlers hanging if queue worker dies:

```python
async def enqueue(self, batch, timeout: float = 30.0) -> list[int]:
    try:
        return await asyncio.wait_for(result_future, timeout)
    except asyncio.TimeoutError:
        raise TelegramQueueTimeout(f"Queue timeout for chat {batch.chat_id}")
```

### 5. EditBatch Enhancement

Add `reply_markup` support to `EditBatch` for keyboard updates:

```python
@dataclass
class EditBatch:
    chat_id: int
    message_id: int
    text: str
    parse_mode: str | None = None
    reply_markup: InlineKeyboardMarkup | None = None  # NEW
```

## Implementation Plan

1. Add timeout to `enqueue()`
2. Add `reply_markup` to `EditBatch`
3. Add helper methods: `reply()`, `send()`, `edit()`
4. Register queue on Dispatcher for DI
5. Update handlers (by file, smallest first)
6. Update services/launch.py
7. Update launch_animation.py
8. Tests for helpers

## Risks

- **Latency**: Queue adds ~1ms overhead (acceptable)
- **Deadlock**: Mitigated by timeout parameter

## Future Enhancements

With all messages through queue:
- Message logging/metrics
- Fix `●` prefix issue (telegramify before prefix)
- Media message support
