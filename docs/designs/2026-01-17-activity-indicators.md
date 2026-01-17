# Activity Indicators

## Overview

Show in Telegram when Claude is thinking/working.

**User sees:**
- When Claude starts thinking → message appears: `· Hatching… (/esc · 42s · ↓ 0 tokens)`
- Message updates every ~3 sec (time, verb, tokens)
- When Claude finishes → message deleted

**Text replacement:** `esc to interrupt` → `/esc` (Telegram command)

## TelegramQueue Changes

**New fields in OutgoingBatch:**
```python
@dataclass
class OutgoingBatch:
    chat_id: int
    thread_id: int | None
    messages: list[dict]
    reply_markup: Any = None
    # New:
    replace_key: str | None = None
    operation: Literal["send", "edit", "delete"] = "send"
    target_msg_id: int | None = None  # for edit/delete
```

**Queue logic:**
1. On `enqueue()` with `replace_key` — find batch with same key in queue, remove old one
2. Store `sent_statuses: dict[str, int]` — mapping `replace_key → msg_id` for sent messages
3. On processing:
   - `operation="send"` → send_message, if replace_key exists — save msg_id to sent_statuses
   - `operation="edit"` → get msg_id from target_msg_id or sent_statuses[replace_key], do edit_message
   - `operation="delete"` → delete_message, remove from sent_statuses

**Structure change:** replace `asyncio.Queue` with `collections.deque` + `asyncio.Lock` for search/replace capability.

## Parsing in screen.py

**New dataclass:**
```python
@dataclass
class ThinkingStatus:
    verb: str      # "Hatching", "Conjuring", "Enchanting"
    seconds: int   # 42
    tokens: int    # 0
```

**New function:**
```python
def parse_thinking_status(output: str) -> ThinkingStatus | None:
    """Parse thinking indicator from tmux output.

    Format: · Hatching… (esc to interrupt · 42s · ↓ 0 tokens)
    Located ABOVE the input box (before first ────).
    """
```

**Parsing logic:**
- Regex: `· (\w+)… \(esc to interrupt · (\d+)s · ↓ (\d+) tokens?\)`
- Search in lines BEFORE first `────` (above input box)
- Return `ThinkingStatus` or `None` if not found

**Not part of ScreenState** — separate function like `parse_status_bar()`.

## Processing in permission_poller

**New poller state:**
```python
# Add to existing
thinking_msg_key: str | None = None  # "thinking:{chat_id}:{thread_id}"
last_thinking_update: float = 0
```

**Logic in main loop:**
```python
# After parse_screen()
thinking = parse_thinking_status(screen)

if thinking:
    now = time.time()
    if now - last_thinking_update >= 3.0:  # throttle 3 sec
        text = f"· {thinking.verb}… (/esc · {thinking.seconds}s · ↓ {thinking.tokens} tokens)"
        key = f"thinking:{chat_id}:{thread_id}"

        if thinking_msg_key is None:
            # First time — send
            batch = OutgoingBatch(..., replace_key=key, operation="send")
            thinking_msg_key = key
        else:
            # Update — edit
            batch = OutgoingBatch(..., replace_key=key, operation="edit")

        await telegram_queue.enqueue(batch)
        last_thinking_update = now

elif thinking_msg_key:
    # Claude finished — delete
    batch = OutgoingBatch(..., replace_key=thinking_msg_key, operation="delete")
    await telegram_queue.enqueue(batch)
    thinking_msg_key = None
```

**Priority:** thinking status doesn't block permission prompt — processed independently.

## Edge Cases

1. **Permission prompt appears while thinking** — delete thinking status, show prompt
2. **Claude finishes between polls** — thinking status deleted on next poll (ok, ~0.5 sec delay)
3. **Message still in queue, delete arrives** — replace_key mechanism removes from queue without sending
4. **Multiple threads** — each poller has own `thinking_msg_key`, keys differ by thread_id

## Testing

- Unit: `parse_thinking_status()` with various formats
- Unit: `TelegramQueue` with replace_key — replace, edit, delete
- E2E: send message to Claude, see thinking status in Telegram, wait for response — status deleted
