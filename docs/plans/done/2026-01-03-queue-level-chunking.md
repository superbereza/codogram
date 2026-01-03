# Queue-Level Chunking Implementation Plan

**Status:** Done
**Date:** 2026-01-03
**Design:** See `docs/designs/done/2026-01-03-queue-level-chunking.md`

## Goal

Centralize message chunking in TelegramQueue to eliminate code duplication.

## Tasks

### Task 1: Add chunking to TelegramQueue._send_batch()

**Files:** `src/codogram/telegram_queue.py`

- Import `chunk_message` from chunker
- Before sending, expand messages >4000 chars
- Preserve all message properties (parse_mode, etc.)

**Done:** Added 8 lines of chunking logic

### Task 2: Remove manual chunking from watcher.py

**Files:** `src/codogram/watcher.py`

- Simplify `_entry_to_messages()` to not chunk
- Delete dead `send_entry_to_telegram()` function (unused since 2025-12-29 refactor)
- Remove `chunk_message` import

**Done:** Deleted 60 lines of dead code, simplified 3 lines

### Task 3: Remove manual chunking from permission_poller.py

**Files:** `src/codogram/permission_poller.py`

- Simplify 4 places that build `body_messages`
- Remove `chunk_message` import

**Done:** Simplified 4 code blocks

### Task 4: Simplify auto_accept.py

**Files:** `src/codogram/auto_accept.py`

- Remove manual chunking loop
- Send single message (queue handles chunking)

**Done:** Already simplified earlier

### Task 5: Add tests for queue chunking

**Files:** `tests/test_telegram_queue.py`

Tests added:
- `test_long_message_chunked` - verifies >4000 char messages are split
- `test_short_message_not_chunked` - verifies ≤4000 char messages unchanged
- `test_chunking_preserves_parse_mode` - verifies parse_mode on all chunks

**Done:** 3 tests, all passing

### Task 6: Documentation

**Files:**
- `docs/designs/done/2026-01-03-queue-level-chunking.md`
- `docs/plans/done/2026-01-03-queue-level-chunking.md`

**Done:** This file

## Results

- **Lines removed:** ~60 (dead code + manual chunking)
- **Lines added:** ~60 (queue logic + tests + docs)
- **Net:** Cleaner, centralized, tested

## Commits

Pending commit with all changes.
