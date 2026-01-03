# Queue-Level Message Chunking

**Status:** Done
**Date:** 2026-01-03

## Problem

Message chunking (splitting long messages >4000 chars) was done manually in 4+ places:
- `watcher.py` - `_entry_to_messages()` and dead `send_entry_to_telegram()`
- `permission_poller.py` - 4 places building `body_messages`
- `auto_accept.py` - notification messages

This led to:
- Code duplication
- Inconsistent behavior
- Risk of missing chunking in new code paths

## Solution

Move chunking into `TelegramQueue._send_batch()` as a centralized safety net.

### Implementation

```python
# telegram_queue.py

async def _send_batch(self, batch: OutgoingBatch, attempt: int = 0) -> list[int]:
    # Expand messages with chunking
    expanded_messages = []
    for msg in batch.messages:
        text = msg.get("text", "")
        if len(text) > 4000:
            for chunk in chunk_message(text):
                expanded_messages.append({**msg, "text": chunk})
        else:
            expanded_messages.append(msg)

    # Send expanded_messages...
```

### Behavior

- Messages ≤4000 chars: pass through unchanged
- Messages >4000 chars: split using `chunk_message()`, preserving other fields (parse_mode, etc.)
- Chunk prefixes like `[1/3]\n` added by chunker

## Changes Made

1. **telegram_queue.py**: Added chunking in `_send_batch()`
2. **watcher.py**:
   - Removed manual chunking from `_entry_to_messages()`
   - Deleted dead `send_entry_to_telegram()` function (unused since 2025-12-29)
   - Removed `chunk_message` import
3. **permission_poller.py**:
   - Removed manual chunking from 4 places
   - Removed `chunk_message` import
4. **auto_accept.py**: Simplified to single message (queue handles chunking)

## Tests Added

```python
test_long_message_chunked()      # Messages >4000 chars split
test_short_message_not_chunked() # Messages ≤4000 chars unchanged
test_chunking_preserves_parse_mode() # parse_mode preserved on all chunks
```

## Trade-offs

### Kept 4000 threshold (not 4096)

Telegram's actual limit is 4096 chars, but we use 4000 to be conservative and match existing `chunk_message()` default. Messages of 4001-4096 chars will be unnecessarily split, but this is safe.

### Bullet point behavior

When watcher sends `● Long text...`:
- **Before:** `● [1/3]\nFirst part`, `● [2/3]\nSecond part`
- **After:** `[1/3]\n● First part`, `[2/3]\nSecond part`

Only the first chunk has the bullet point now. User confirmed this is acceptable.

## Future Considerations

- Could add logging when queue chunks (to catch callers not pre-formatting)
- Could expose chunking options (custom prefixes, different thresholds)
