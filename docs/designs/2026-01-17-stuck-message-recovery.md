# Design: Stuck Message Recovery

**Date:** 2026-01-17
**Status:** Draft
**Related bug:** `docs/bugs/2026-01-17-stuck-message-in-input.md`

## Problem

Messages sometimes get stuck in Claude's input line without being submitted. User sees their message but Claude doesn't process it.

## Goal

Automatically detect stuck messages and push them through by sending Enter.

## Constraints

1. **Don't confuse with suggestions** — Claude shows autocomplete suggestions in input area
2. **Don't interrupt typing** — if user is manually typing in tmux, don't interfere
3. **Debounce** — require seeing same stuck text twice before acting

## Detection criteria

Send Enter only if input line contains:

1. **Pasted placeholder**: `[Pasted X lines]` pattern
2. **Last sent message**: exact match with `thread.last_sent_message`

NOT suggestions because:
- Suggestions appear differently (greyed out, after cursor)
- Suggestions don't match `last_sent_message`
- `[Pasted X lines]` is never a suggestion

## Implementation

### 1. Add input line parser

```python
# screen.py

import re

PASTED_PATTERN = re.compile(r'\[Pasted \d+ lines?\]')

def extract_input_text(screen: str) -> str | None:
    """Extract text from Claude's input line (after ❯).

    Returns None if input is empty or not found.
    """
    for line in screen.split("\n"):
        stripped = line.strip()
        if stripped.startswith("❯"):
            # Text after ❯ and space
            text = stripped[1:].strip()
            return text if text else None
    return None
```

### 2. Add stuck detection to poller

```python
# permission_poller.py

from .screen import extract_input_text, PASTED_PATTERN

# In permission_poller() function, add state variables:
stuck_input_text: str | None = None
stuck_seen_count: int = 0

# In the polling loop, after crash detection but before state machine:

input_text = extract_input_text(screen)
if input_text:
    last_msg = thread.last_sent_message if thread else None

    is_potentially_stuck = (
        PASTED_PATTERN.match(input_text) or
        (last_msg and input_text == last_msg)
    )

    if is_potentially_stuck:
        if input_text == stuck_input_text:
            stuck_seen_count += 1
        else:
            stuck_input_text = input_text
            stuck_seen_count = 1

        # Debounce: seen twice = stuck
        if stuck_seen_count >= 2:
            logger.info(f"{log_prefix}: stuck message detected, sending Enter")
            tmux.send_key("Enter")
            stuck_input_text = None
            stuck_seen_count = 0
    else:
        stuck_input_text = None
        stuck_seen_count = 0
else:
    stuck_input_text = None
    stuck_seen_count = 0
```

### 3. Clear last_sent_message after successful send

Currently `last_sent_message` is set but never cleared. Add clearing after Enter is sent:

```python
# After sending Enter for stuck message:
if thread:
    thread.last_sent_message = None
```

## Edge cases

| Case | Behavior |
|------|----------|
| User typing in tmux | `last_sent_message` won't match, no action |
| Suggestion shown | Suggestions don't match patterns, no action |
| Same message sent twice | Will recover both times |
| Bot restart | `last_sent_message` may be None, only `[Pasted]` detection works |
| Permission prompt visible | Poller in SHOWING state, input extraction still works |

## Testing

### Manual test

1. Send long multi-line message
2. Verify it appears in Claude input
3. If stuck (not submitted):
   - Wait 2 poll intervals (~1 sec)
   - Should auto-recover with Enter

### E2E test

```
Send message: "Test message for stuck detection"
Wait 3 seconds
Check Claude responded (message was delivered)
```

## Alternatives considered

### A: Fix in tmux.send() instead

Could add verification in `send()` method:
```python
# After sending Enter, verify input is empty
time.sleep(0.5)
screen = self.capture_pane()
if extract_input_text(screen):
    subprocess.run(["tmux", "send-keys", "-t", self.name, "Enter"])
```

**Rejected because:**
- Adds latency to every send
- `send()` is synchronous, blocking
- Better to handle asynchronously in poller

### B: Increase sleep between text and Enter

```python
time.sleep(0.5)  # Instead of 0.3
```

**Rejected because:**
- Doesn't guarantee fix
- Adds latency to every message
- Root cause is race condition, not timing

## Checklist

- [ ] Add `extract_input_text()` to screen.py
- [ ] Add `PASTED_PATTERN` to screen.py
- [ ] Add stuck detection logic to permission_poller.py
- [ ] Clear `last_sent_message` after recovery
- [ ] Add logging for debugging
- [ ] Test with multi-line messages
- [ ] Test with large messages
