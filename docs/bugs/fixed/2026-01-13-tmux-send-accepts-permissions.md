# tmux.send() accidentally accepts permission prompts

**Date:** 2026-01-13
**Severity:** Critical
**Status:** Fixed

## Symptom

When user sends a message through Telegram while a permission prompt is active in Claude CLI:
- Message does NOT reach Claude
- Permission gets accepted (Yes selected)
- Appears as if auto_accept is ON, but it's actually OFF

User report: "каждый следующий текст срабатывал как акцепт, а не как отправка текста"

## Root Cause

`tmux.send()` blindly sends `C-c → text → Enter`:

```python
# tmux.py lines 39-66
# Step 1: Send C-c
subprocess.run(["tmux", "send-keys", "-t", self.name, "C-c"], check=True)
# Step 2: Send text with -l (literal)
subprocess.run(["tmux", "send-keys", "-t", self.name, "-l", "--", text], check=True)
# Step 3: Send Enter
subprocess.run(["tmux", "send-keys", "-t", self.name, "Enter"], check=True)
```

When permission prompt is active:
1. **C-c is ignored** - Claude doesn't respond to C-c in permission mode
2. **Text goes nowhere** - there's no input field, text is discarded
3. **Enter selects current option** - usually `❯ 1. Yes`

## Evidence

From `logs/tmux-send-debug.log` at 05:26:55 EST:

```
BEFORE:
Do you want to proceed?
❯ 1. Yes
  2. Yes, and don't ask again for PYTHONPATH=src python -m pytest...
  3. No
Esc to cancel

[1] Sending C-c...
AFTER C-c:
❯ 1. Yes         <-- prompt still there, C-c ignored

[2] Sending text with -l...
AFTER text:
❯ 1. Yes         <-- prompt still there, text went nowhere

[3] Sending Enter...
AFTER Enter:
                 <-- prompt gone, pytest started (Yes was selected!)
```

Compare to 05:28:26 when NO permission prompt was active - message went through normally.

## Impact

- Messages lost silently
- Unwanted permission grants
- User confusion ("I turned off auto_accept but it still accepts!")

## Fix

Added `_cancel_permission_if_active()` method to `TmuxSession`:

```python
def _cancel_permission_if_active(self, max_attempts: int = 3) -> bool:
    """Cancel permission prompt if active."""
    from .screen import parse_screen, PermissionPrompt

    for attempt in range(max_attempts):
        output = self.capture_pane()
        state = parse_screen(output)

        if not isinstance(state, PermissionPrompt):
            return True

        subprocess.run(["tmux", "send-keys", "-t", self.name, "Escape"], check=True)
        time.sleep(0.2)

    return False
```

Called at the start of `send()` before sending C-c/text/Enter.

Now when user sends a message while permission prompt is active:
1. `parse_screen()` detects the prompt
2. Escape is sent to cancel it
3. Message is delivered to Claude normally

## Related

- `src/codogram/tmux.py` - send() method
- `src/codogram/screen.py` - has permission parsing functions
- `src/codogram/handlers/messages.py` - routes user messages to tmux.send()
