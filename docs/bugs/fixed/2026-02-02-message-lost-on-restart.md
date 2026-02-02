# Bug: Messages lost on bot restart

**Date:** 2026-02-02
**Severity:** High
**Status:** Fixed

## Summary

Messages from Claude were lost when bot restarted during active conversation. The watcher started reading from end of jsonl file, missing messages written before restart.

## Root Cause

`JsonlWatcher` initialized `last_position` to current file size:

```python
# OLD CODE (buggy):
self.last_position = path.stat().st_size if path.exists() else 0
```

This meant any messages written between:
1. Last message sent to Telegram
2. Bot restart

...were never delivered.

## Timeline example

```
02:02:15 - User sends message to Claude
02:02:20 - Claude writes response to jsonl
02:02:33 - Bot restarts (watcher cancelled)
02:02:44 - Watcher starts with position=file_size (end of file)
02:02:44 - Claude's response at 02:02:20 is SKIPPED
```

## Fix

1. Added `jsonl_position` field to `ThreadInfo`
2. Save position to config after each message is sent
3. Load position on watcher startup

```python
# NEW CODE:
def __init__(self, path: Path, poll_interval: float | None = None, initial_position: int | None = None):
    if initial_position is not None:
        self.last_position = initial_position
    else:
        self.last_position = path.stat().st_size if path.exists() else 0
```

And in `watch_thread_jsonl`:
```python
# Update position after successful send
new_position = watcher.get_position()
if new_position != thread.jsonl_position:
    thread.jsonl_position = new_position
    project_manager._save()
```

## Files changed

- `src/codogram/core/session_manager.py` - added `jsonl_position` field, persist/load
- `src/codogram/claude/history_watcher.py` - accept `initial_position`, save after send

## Verification

After fix, watcher startup shows saved position:
```
thread_watcher_started: thread=less-noise, session=62815ea8, position=37416452
```

## Related

- `docs/bugs/active/2026-02-01-subagent-message-lost-race-condition.md` - different bug (race condition in subagent file reading)
