# Auto-accept trust folder prompt spam

**Date:** 2026-01-17
**Status:** Fixed

## Symptoms

1. "Do you trust the files in this folder?" prompt was auto-accepted (should require manual confirmation)
2. Auto-accept triggered 5 times for the same prompt, spamming the chat

## Root Cause

### Bug 1: Trust folder classified as REGULAR

`_parse_options_without_separator()` in `screen.py` returns `PermissionPrompt` without setting `prompt_type`, defaulting to `REGULAR`. Trust folder prompts don't have the `────` separator, so they're parsed by this function and incorrectly classified.

```python
# Before fix
return PermissionPrompt(options=options, body=body)  # prompt_type defaults to REGULAR
```

### Bug 2: No dedup after auto_accept

After auto_accept in `permission_poller.py`, state was reset to `IDLE` with `last_options = None`:

```python
# Before fix
if await try_auto_accept(...):
    state = PollerState.IDLE
    last_options = None  # Reset!
    continue
```

On next poll iteration (0.5s), the prompt is still visible (Claude processing), so:
1. `state == IDLE`, `is_permission == True` → transition to `DEBOUNCING`
2. Wait debounce time
3. Auto_accept again
4. Repeat until Claude removes the prompt

## Fix

### Bug 1: Detect trust-related prompts

In `screen.py`, detect "trust" or "folder" keywords and set `MCP_TRUST` type (excluded from auto_accept):

```python
body_lower = body.lower()
if "trust" in body_lower or "folder" in body_lower:
    return PermissionPrompt(options=options, body=body, prompt_type=PromptType.MCP_TRUST)
```

### Bug 2: Reuse SHOWING state for dedup

After auto_accept, transition to `SHOWING` instead of `IDLE` to reuse existing dedup logic:

```python
if await try_auto_accept(...):
    state = PollerState.SHOWING  # Reuse dedup logic
    last_body = parsed.body
    continue
```

In `SHOWING` state, if prompt is still visible with same options/body, nothing happens. When prompt disappears, normal cleanup to `IDLE`.

## Files Changed

- `src/codogram/screen.py` - detect trust prompts
- `src/codogram/permission_poller.py` - fix state transition after auto_accept
