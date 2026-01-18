# Bug: Magic name collision after restart

**Date:** 2026-01-01
**Severity:** High
**Status:** Open

## Summary

After bot restart, threads can lose their bindings and get assigned magic names that are already in use by other threads/tmux sessions.

## Reproduction steps

1. Have multiple threads with magic names (e.g., thread 1256 = "sublime", thread 1038 = "immortal")
2. Restart the bot
3. Send a message in thread 1038 before pressing /start
4. Press /start in thread 1038
5. **Bug:** Thread 1038 gets assigned "sublime" even though it's already used by thread 1256

## Root cause

Two separate bugs combine:

### Bug 1: Thread not restored from config

After restart, thread 1038 had `name='pending'` instead of the saved `name='immortal'`. Possible causes:
- Config wasn't saved before crash
- Thread wasn't loaded correctly from config
- First message to topic created new pending thread before config was checked

### Bug 2: Magic name collision

When assigning magic names (`bot.py:320-321`):

```python
existing_names = {t.name for t in project.threads.values() if t.name != "pending"}
thread.name = get_random_magic_name(existing_names)
```

This only checks `project.threads` but **doesn't check existing tmux sessions**. If threads weren't loaded correctly, `existing_names` is incomplete and an already-used name can be picked.

## Evidence from logs

```
2026-01-01 06:55:01 cmd_start: thread_id=1038, name='pending'   # Should be 'immortal'
2026-01-01 06:55:01 tmux_send: session=claude-codogram-sublime  # Collision with thread 1256!
2026-01-01 06:55:02 Permission poller started for thread sublime
```

Current config shows:
- Thread 1256 = "sublime"
- Thread 1038 = "immortal"

But at 06:55:01, thread 1038 was assigned "sublime", causing collision.

## Impact

- Thread gets connected to wrong tmux session
- User sees responses from different Claude session
- Confusion about which session is active
- Potential data/context mixup between threads

## Proposed fix

### Fix 1: Check existing tmux sessions

```python
# bot.py - when assigning magic name
existing_names = {t.name for t in project.threads.values() if t.name != "pending"}

# Also check existing tmux sessions
from .tmux import get_existing_tmux_suffixes
existing_tmux = get_existing_tmux_suffixes(project.project_name)
existing_names.update(existing_tmux)

thread.name = get_random_magic_name(existing_names)
```

### Fix 2: Add tmux helper function

```python
# tmux.py
def get_existing_tmux_suffixes(project_name: str) -> set[str]:
    """Get all existing tmux session suffixes for a project."""
    import subprocess
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return set()

    prefix = f"claude-{project_name}-"
    suffixes = set()
    for line in result.stdout.strip().split('\n'):
        if line.startswith(prefix):
            suffix = line[len(prefix):]
            if suffix:
                suffixes.add(suffix)
    return suffixes
```

### Fix 3: Investigate config loading

Need to understand why thread 1038 wasn't restored with correct name. Possible improvements:
- Add logging to `_load_projects()` to track which threads are loaded
- Verify config file integrity after restart
- Add validation that loaded threads match saved threads

## Affected code

- `src/codogram/bot.py:317-341` - `/start` command handling
- `src/codogram/bot.py:1326-1331` - pending thread creation
- `src/codogram/session_manager.py:153-188` - `_load_projects()`

## Related

- [Thread session mixup fix](fixed/2025-12-29-session-binding-race-condition.md)
- [/tmp fallback bug](fixed/2025-12-30-tmp-fallback-in-tmux-session.md)
