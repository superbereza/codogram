# tmux.send() accidentally accepts permission prompts

**Date:** 2026-01-13
**Severity:** Critical
**Status:** Active

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

Before sending, check if permission prompt is active:

```python
def send(self, text: str) -> None:
    # Check if permission prompt is active
    screen = self.capture_pane()
    if self._has_permission_prompt(screen):
        logger.warning(f"Cannot send - permission prompt active")
        # Option 1: Don't send, notify caller
        raise PermissionPromptActiveError()
        # Option 2: Send Escape first to cancel prompt
        # self.send_key("Escape")
        # time.sleep(0.1)

    # ... existing send logic ...
```

Or integrate with permission_poller - if prompt detected, don't allow text messages.

## Workaround

User must cancel permission prompt (press Cancel button in Telegram) before sending messages.

## Related

- `src/codogram/tmux.py` - send() method
- `src/codogram/screen.py` - has permission parsing functions
- `src/codogram/handlers/messages.py` - routes user messages to tmux.send()
