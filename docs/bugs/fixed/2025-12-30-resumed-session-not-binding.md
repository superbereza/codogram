# Bug: Resumed sessions not binding after /start

**Date:** 2025-12-30
**Severity:** Medium
**Status:** Fixed

## Summary

When user does `/resume` in Claude CLI (instead of starting a new session), the session doesn't bind to the Telegram thread. Messages from Claude don't appear in Telegram.

## Reproduction steps

1. Have a thread with Claude session that crashed or was closed
2. Press `/start` in Telegram thread
3. In tmux, run `/resume` in Claude CLI to continue old session
4. Send message from Telegram
5. **Bug:** Session never binds, messages don't come through

## Root cause

The session binding logic filtered by **creation time**:

```python
session_created = get_session_creation_time(jsonl_path)
if session_created < created_after:
    continue  # Session created before /start - skip
```

When user does `/resume`, Claude continues an OLD session (created before `/start`). This session gets filtered out even though it's now active.

## Fix

Changed `find_session_by_user_message` to filter by **modification time** (mtime) instead of creation time:

```python
session_mtime = jsonl_path.stat().st_mtime
if session_mtime < created_after:
    continue  # Session not modified since /start - skip
```

This supports both:
- **New sessions:** created after /start → mtime > start_requested_at ✓
- **Resumed sessions:** old but modified after /start → mtime > start_requested_at ✓
- **Old inactive sessions:** not modified → mtime < start_requested_at → filtered ✓

## Files changed

- `src/codogram/history_reader.py:230-236` - Changed from creation time to mtime

## Commits

- `8765b8e` fix(watcher): use mtime instead of creation time for session binding

## Related

- [Session binding race condition](2025-12-29-session-binding-race-condition.md) - Original fix that added time filtering
