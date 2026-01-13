# Watcher not restarted after /clear or /new

**Date:** 2026-01-13
**Severity:** High
**Status:** Fixed

## Symptom

After `/clear` or `/new` command:
- Permission prompts work (shown in Telegram, buttons clickable)
- But Claude's text responses don't appear in Telegram
- User reports "3 messages in tmux but only 1 received in Telegram"

## Root Cause

In `sessions.py`, `/clear` and `/new` set `session_id = None` but **don't cancel the old watcher_task**.

```python
# Before fix - sessions.py _send_session_command()
thread.awaiting_new_session = True
thread.start_requested_at = time.time()
thread.last_sent_message = None
thread.session_id = None  # Clear so next message triggers rebinding
# BUG: watcher_task still running with old jsonl!
```

Later, when `poll_for_session_thread` binds to new session:

```python
# history_watcher.py poll_for_session_thread()
if not thread.watcher_task or thread.watcher_task.done():
    thread.watcher_task = asyncio.create_task(
        watch_thread_jsonl(bot, project, thread, telegram_queue)
    )
```

The condition fails because old `watcher_task` is still active → new watcher **not created** → new jsonl **not watched**.

## Evidence

From logs at 13:20 EST:

```
13:20:01 tmux_send: session=claude-codogram-show-thinking-status text='/clear'
13:20:17 session_bound_thread: thread=show-thinking-status, session=ac589a13
13:20:17 thread_watcher_started: thread=show-thinking-status, session=ac589a13
```

But no `message_read` logs for show-thinking-status after binding!
All `message_read` logs go to thread=main only.

The `thread_watcher_started` log comes from `poll_for_session_thread` (line 351),
NOT from `watch_thread_jsonl` (line 252), because new watcher was never created.

## Fix

Cancel old watcher_task before setting `awaiting_new_session`:

```python
# sessions.py _send_session_command()
if thread.watcher_task:
    thread.watcher_task.cancel()
    thread.watcher_task = None

thread.awaiting_new_session = True
...
```

Now `poll_for_session_thread` condition succeeds and new watcher is created.

## Related

- `src/codogram/handlers/sessions.py` - /clear, /new handlers
- `src/codogram/history_watcher.py` - poll_for_session_thread, watch_thread_jsonl
