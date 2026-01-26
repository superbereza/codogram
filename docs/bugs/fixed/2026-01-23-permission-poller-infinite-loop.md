# Permission poller infinite loop on options change

**Date:** 2026-01-23
**Severity:** Critical
**Status:** Fixed

## Summary

Permission poller enters infinite loop when permission prompt options change (e.g., two consecutive Fetch requests to different domains). Poller continuously sends and deletes permission messages.

## Reproduction

1. Claude makes two Fetch requests in quick succession (e.g., `raw.githubusercontent.com` then `github.com`)
2. User clicks permission button for first request
3. Claude accepts and immediately shows second permission prompt
4. Poller detects "options changed" and resends
5. Loop: poller keeps detecting change and resending every cycle

## Timeline from logs

```
15:10:25 SHOWING: sent 3 options for raw.githubusercontent.com
15:10:27 User clicks "Yes, don't ask again" (key=2 sent)
15:10:28 Claude shows NEW prompt for github.com
15:10:28 SHOWING: options/body changed! → resend
15:10:28 SHOWING: options/body changed! → resend
... (infinite loop)
```

## Root cause

In `_send_permission()` (permissions.py:169):
```python
self.last_body = parsed.body
# BUG: self.last_options was NOT updated!
```

After resend, `last_options` stays stale. Next poll cycle:
- `parsed.options != self.last_options` → TRUE (always)
- Triggers another resend → infinite loop

## Fix

Added missing line in `_send_permission()`:
```python
self.last_body = parsed.body
self.last_options = parsed.options  # ← Added
```

## Affected file

`src/codogram/claude/poller/processors/permissions.py:170`
