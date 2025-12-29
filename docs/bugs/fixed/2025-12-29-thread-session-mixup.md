# Bug: Thread session mixup when new session appears in another thread

**Date:** 2025-12-29
**Severity:** High
**Status:** Fixed

## Resolution

**Fixed by:** [Session Binder Telegram Commands](../plans/2025-12-29-session-binder-telegram-commands.md)

**Fix summary:**
- Removed `check_session_for_thread` — the function that incorrectly detected session changes
- Added explicit `/new` and `/clear` Telegram commands with `awaiting_new_session` flag
- Added `_bind_awaiting_threads` that only binds threads explicitly waiting for new session
- Now threads maintain independent session bindings; new session in one thread doesn't affect others

**Commits:** `8998627`, `79992b0`, `7d212e0`, `04f0e2f`, `5d7f65a`, `4db681b`, `505b844`

---

## Summary

When a new Claude session is created in one thread (e.g., General/main), other threads incorrectly detect a "session change" and lose their session binding. This causes the watcher to stop monitoring the thread's jsonl file, and messages from Claude no longer appear in Telegram.

## Reproduction steps

1. Have two active threads in a project:
   - General (main) with session `A`
   - Topic "sublime" (thread 1256) with session `B`
2. Both watchers are running, messages flow normally
3. Start a new Claude session in General → new session `C` appears
4. Send a message in the "sublime" topic
5. **Bug:** sublime's watcher gets cancelled, session_id becomes null

## What happened (from logs)

```
08:31:58 [INFO] Incoming message from user=34185809 chat=-1003532995083 thread=1256: У меня комментарий
08:31:58 [DEBUG] Message routing: project=codogram thread_id=1256 thread=ThreadInfo(..., session_id='405fe3e1-03e6-409d-b7c7-c15262240429', ...)
08:31:58 [INFO] session_changed_thread: project=codogram, thread=sublime, old=405fe3e1, new=14c5fa0c
08:31:59 [INFO] watch_thread_cancelled: thread=sublime
```

Key issue: `session_changed_thread` detected session change from `405fe3e1` (sublime's real session) to `14c5fa0c` (main's session). This is incorrect.

## Root cause

The `session_changed_thread` logic polls `history.jsonl` to find the "current session" for a project. However:

1. `history.jsonl` contains ALL sessions for a project, not per-thread
2. When checking for session changes, the code finds the **latest** session in history.jsonl
3. If another thread (main) has a newer session, it's incorrectly detected as "this thread's session changed"
4. The thread's watcher is cancelled and session_id is set to null

### Code flow (suspected)

```
on_message(thread=sublime)
  → check history.jsonl for project "codogram"
  → find latest session: 14c5fa0c (this is main's session!)
  → compare with sublime's session_id: 405fe3e1
  → mismatch! → trigger session_changed_thread
  → cancel sublime's watcher
  → set sublime's session_id = null (or to wrong session)
```

## Expected behavior

Each thread should maintain its own session binding independently. A new session in one thread should NOT affect other threads.

## Possible fixes

### Option 1: Bind sessions by tmux session name

Each thread has a dedicated tmux session (e.g., `claude-codogram-sublime`). Use tmux session name as the source of truth:

```python
# When routing message to thread
tmux_session = f"claude-{project}-{thread_name}"
# Only change session_id if it came from THIS tmux session
```

### Option 2: Don't auto-detect session changes for existing threads

If a thread already has a valid session_id AND the tmux session is alive, don't try to "update" the session from history.jsonl:

```python
if thread.session_id and tmux_session_exists(thread.tmux_session):
    # Keep existing session, don't poll history.jsonl
    pass
```

### Option 3: Track session↔thread mapping explicitly

When a session is created via `/start` in a thread, store the mapping:

```python
# In history.jsonl polling, only update thread's session if:
# 1. Thread has no session (session_id is None)
# 2. OR the session in history.jsonl was created AFTER last message in this thread
```

### Option 4: Use tmux capture-pane to get session_id

Instead of relying on history.jsonl, parse the session_id from the tmux pane for each thread independently.

## Affected files (likely)

- `src/codogram/session_manager.py` - session change detection logic
- `src/codogram/history_reader.py` - history.jsonl polling
- `src/codogram/watcher.py` - watcher lifecycle management

## Workaround

Run `/start` in the affected topic to re-bind the session.

## Related

- Multi-session topics architecture (docs/designs/)
- Session binding logic
