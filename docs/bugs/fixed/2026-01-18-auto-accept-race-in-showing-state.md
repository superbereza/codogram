# Bug: Auto-accept race condition in SHOWING state

**Date:** 2026-01-18
**Severity:** Medium
**Status:** Fixed
**Commit:** 0ddc585

## Summary

When auto-accept is enabled, permission prompts sometimes still show buttons in Telegram instead of being auto-accepted.

## Reproduction steps

1. Enable auto-accept for a thread
2. Claude requests permission (e.g., Bash command)
3. Auto-accept sends key "1" to tmux
4. Before prompt disappears, tmux capture returns slightly different body/options
5. Bot sends buttons to Telegram (ignoring auto_accept setting)

## Root cause

Race condition in `permission_poller.py` SHOWING state handler.

When auto-accept sends key "1", the poller transitions to SHOWING state to wait for prompt to disappear. However, if `body` or `options` change slightly (due to tmux capture timing), the code at line 451 would:

1. Detect `parsed.options != last_options or parsed.body != last_body`
2. Delete old messages and send NEW ones with buttons
3. **Without checking auto_accept setting!**

```python
elif parsed.options != last_options or parsed.body != last_body:
    logger.debug(f"{log_prefix} SHOWING: body/options changed, resending")
    # ... sends buttons to Telegram without checking auto_accept
```

## Evidence

From logs:
```
05:37:18 IDLE->DEBOUNCING: detected permission, options=['1. Yes', '2. Yes, allow reading from codogram/', '3. No']
05:37:18 auto_accept show-thinking-status option=1
05:37:18 tmux_send_key: session=claude-codogram-show-thinking-status key=1
05:37:19 SHOWING: body/options changed, resending
```

Auto-accept worked at 05:37:18, but 1 second later the poller saw a "change" and sent buttons.

## Fix

Added auto_accept check in SHOWING state before resending buttons:

```python
elif parsed.options != last_options or parsed.body != last_body:
    # Check auto-accept first (race condition: prompt may change before tmux processes key)
    auto_accept_enabled = thread.auto_accept if thread else project.auto_accept
    if auto_accept_enabled:
        if await try_auto_accept(...):
            logger.debug(f"{log_prefix} SHOWING: body/options changed, auto-accepted again")
            last_options = parsed.options
            last_body = parsed.body
            continue

    logger.debug(f"{log_prefix} SHOWING: body/options changed, resending")
    # ... send buttons only if auto_accept failed
```

## Affected code

- `src/codogram/permission_poller.py:451-502` - SHOWING state handler
