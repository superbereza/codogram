# TelegramQueue Cleanup

**Date:** 2025-01-04
**Priority:** Low
**Found during:** Unified Message Queue implementation (code review)

## Issues

### 1. DRY: Item creation duplication
**Location:** `telegram_queue.py` - `enqueue()` and `enqueue_nowait()`

Both methods duplicate the same item creation logic:
```python
if isinstance(batch, EditBatch):
    item = _EditQueueItem(batch=batch, result=...)
elif isinstance(batch, KeyboardBatch):
    item = _KeyboardQueueItem(batch=batch, result=...)
else:
    item = _QueueItem(batch=batch, result=...)
```

**Fix:** Extract to `_create_queue_item(batch, wait=True)` helper.

### 2. `_send_keyboard()` missing retry logic
**Location:** `telegram_queue.py:_send_keyboard()`

Unlike `_send_batch()`, this method lacks proper retry logic:
- No `MAX_ATTEMPTS` limit
- No `_cleanup_orphans()` on failure
- Catches generic `Exception` instead of specific errors

**Fix:** Align with `_send_batch()` pattern.

### 3. Magic strings
**Location:** `telegram_queue.py` - two places

`"parse entities"` hardcoded in:
- `_send_batch()` line ~239
- `_edit_message()` line ~297

**Fix:** Extract to `PARSE_ERROR_SUBSTRING = "parse entities"` constant.

### 4. `MAX_ATTEMPTS` duplication
**Location:** `telegram_queue.py`

`MAX_ATTEMPTS = 3` defined locally in:
- `_send_batch()`
- `_edit_message()`

**Fix:** Move to class constant `MAX_SEND_ATTEMPTS = 3`.

### 5. Incomplete type hints
**Location:** `telegram_queue.py` - helper methods

`msg_dict: dict` should be `dict[str, Any]`.

**Fix:** Add `from typing import Any` and update type hints.

### 6. Missing docstrings
**Location:** `telegram_queue.py:enqueue_nowait()`

No documentation for parameters and fire-and-forget semantics.

**Fix:** Add parameter docstrings.

## Impact

- None of these affect functionality
- All tests pass
- Code works correctly
- These are maintainability improvements
