# Bug: jsonl_position not reset when session changes

**Date:** 2026-02-02
**Severity:** High
**Status:** Fixed

## Summary

Messages lost after `/clear` or new session creation. The watcher used old session's position for new session's jsonl file, causing it to skip all content.

## Root Cause

When session changes (e.g., after `/clear`), `session_id` and `jsonl_path` are updated but `jsonl_position` was not reset:

```python
# OLD CODE (buggy):
thread.session_id = new_session_id
thread.jsonl_path = str(jsonl_path)
# jsonl_position still has old value!
```

## Timeline example

```
08:28:44 - Session d26e27b0 bound, position saved as 18067195
08:33:39 - User sends /clear
08:35:13 - New session fa3c5223 bound
08:35:13 - Watcher starts with position=18067195 (from OLD session!)
08:35:13 - New file size is only 12103 bytes
08:35:13 - position > file_size → watcher reads nothing
```

## Evidence

```
session=fa3c5223, position=18067195
file size: 12103 bytes
```

Position was 18MB but file was only 12KB → all messages skipped.

## Fix

Reset `jsonl_position` when session changes:

```python
# NEW CODE:
thread.session_id = new_session_id
thread.jsonl_path = str(jsonl_path)
thread.jsonl_position = None  # Reset for new session file
```

Applied in two places in `coordinator.py`:
1. `poll_for_session_thread()` - initial binding
2. `_rebind_thread_to_session()` - session change detection

## Files changed

- `src/codogram/core/coordinator.py` - reset jsonl_position on session change

## Verification

After fix, watcher starts with `position=None` for new sessions and reads from beginning.
