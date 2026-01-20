# Bug: All threads rebind when new session appears

**Date:** 2026-01-17
**Severity:** Critical
**Status:** Active

## Summary

When a new Claude session appears in the project directory (e.g., after `/new` in Claude terminal), ALL threads get rebound to the new session instead of only threads with `awaiting_new_session=True`.

## Reproduction steps

1. Have project with multiple threads, each bound to different sessions
2. In Claude terminal, run `/new` to start new session
3. Run `/resume` to go back to old session
4. **Bug:** History watcher finds new session and rebinds ALL threads to it

## Evidence from logs

```
18:52:27 session_bound: project=codogram, thread=main, old=626d078f, new=77bf4764
18:52:43 session_bound: project=codogram, thread=onboarding, old=799c6b4a, new=77bf4764
18:52:58 session_bound: project=codogram, thread=debug-sending, old=a6954ec9, new=77bf4764
18:53:14 session_bound: project=codogram, thread=session-state-display, old=f5c7c2ba, new=77bf4764
18:53:30 session_bound: project=codogram, thread=refaktor-strings, old=dc6bb5f6, new=77bf4764
```

All threads rebound to same session `77bf4764` every 15 seconds (polling interval).

## Expected behavior

Only threads with `awaiting_new_session=True` should be rebound.

## Affected code

- `src/codogram/history_watcher.py` - `_bind_awaiting_threads()` function

## Root cause hypothesis

Either:
1. `awaiting_new_session` is being set to `True` on all threads somewhere
2. `_bind_awaiting_threads()` has a bug that ignores the flag
3. There's another code path that binds without checking the flag

## Investigation findings (2026-01-17 evening)

### Timeline reconstruction
```
18:45:13 - Bot received SIGTERM, shut down
18:45:18 - Bot restarted, restored projects from config
18:52:01 - User typed "/new" in Claude terminal (not via Telegram)
18:52:07 - Claude responded to /new, created new session 77bf4764
18:52:27 - First binding: main thread bound to 77bf4764
18:52:43 - Second binding: onboarding thread bound
... (each 15 seconds - polling interval)
18:53:30 - Last binding: refaktor-strings thread bound
```

### Code analysis
- `_bind_awaiting_threads()` has correct check: `if not thread.awaiting_new_session: continue`
- Only 2 places set `awaiting_new_session=True`:
  - `handlers/sessions.py:53` - /new, /clear, /resume commands from Telegram
  - `launch_animation.py:96` - when launching new Claude session
- Neither should have been triggered by typing `/new` directly in Claude terminal

### Verified not the cause
- Python boolean check works correctly: `not None` → skip, `not False` → skip, only `not True` → process
- Config loading uses proper defaults: `thread_data.get("awaiting_new_session", False)`
- No bulk operations that set `awaiting_new_session` on multiple threads

### Still unexplained
- How did ALL 5 threads have `awaiting_new_session=True` at that moment?
- Config doesn't retain history, so we can't verify past state

### Proposed fixes
1. Add debug logging in `_bind_awaiting_threads()`:
   ```python
   for thread in project.threads.values():
       logger.debug(f"bind_check: thread={thread.name} awaiting={thread.awaiting_new_session}")
       if not thread.awaiting_new_session:
           continue
   ```

2. Log when `awaiting_new_session` is set to True:
   ```python
   # In handlers/sessions.py and launch_animation.py
   logger.info(f"awaiting_set_true: thread={thread.name}")
   thread.awaiting_new_session = True
   ```

3. Use explicit boolean check (defensive):
   ```python
   if thread.awaiting_new_session is not True:
       continue
   ```

## Workaround

Manually fix config.json to point threads back to correct sessions.
