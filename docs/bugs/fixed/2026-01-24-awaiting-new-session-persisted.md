# awaiting_new_session persisted causing wrong bindings after restart

**Date:** 2026-01-24
**Severity:** High
**Status:** Fixed

## Summary

`awaiting_new_session` flag was persisted in config. After bot restart, threads with stale `awaiting=True` would bind to random new sessions, causing messages to go to wrong Claude sessions.

## Reproduction

1. User does /start in thread A
2. Bot sets `awaiting_new_session=True`
3. Bot crashes/restarts before binding completes
4. On restart, thread A still has `awaiting=True` in config
5. User creates new session in General (thread B)
6. Coordinator sees new session, binds it to thread A (wrong!)
7. Messages in thread A go to wrong session

## Evidence from logs

```
02:44:15 bind_check: thread=not-sent-message-bug awaiting=True
02:44:15 session_bound: project=codogram, thread=not-sent-message-bug, old=238b6753, new=5b7373b2
```

Thread `not-sent-message-bug` had stale `awaiting=True` from previous run. When user created session `5b7373b2` in General, coordinator bound it to wrong thread.

## Root cause

`awaiting_new_session` and `start_requested_at` were persisted in config.json. These are runtime-only state that should reset on restart.

## Fix

1. Removed from serialization (session_manager.py):
```python
thread_data = {
    "name": t.name,
    "session_id": t.session_id,
    # NOTE: awaiting_new_session and start_requested_at are NOT persisted
    # They are runtime-only state that should reset on bot restart
}
```

2. Removed from loading - always use defaults (False/None)

3. Cleaned 136 stale fields from existing config

## Why not persist?

- Normal /start flow completes in seconds - no persistence needed
- "Recovery" after crash is unreliable - may bind wrong session
- User can just /start again if needed
- Cost of wrong binding >> cost of re-doing /start

## Affected files

- `src/codogram/core/session_manager.py` - removed serialization/loading
- `~/.codogram/config.json` - cleaned stale fields
