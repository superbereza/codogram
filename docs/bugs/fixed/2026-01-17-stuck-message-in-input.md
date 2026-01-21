# Bug: Message stuck in Claude input line

**Date:** 2026-01-17
**Severity:** Medium
**Status:** Open

## Summary

Sometimes when sending a message to Claude via tmux, the message gets stuck in the input line and doesn't get submitted. User sees their message in Claude's input but Claude doesn't process it.

Two variants observed:
1. **Pasted placeholder**: Claude shows `[Pasted X lines]` instead of actual text
2. **Text stuck**: Actual message text visible in input line but Enter wasn't processed

## Reproduction steps

1. Send a message from Telegram to Claude
2. Message appears in Claude's input line (after `❯`)
3. But Enter key wasn't processed — message stays in input, not submitted

Happens intermittently, more likely with:
- Large messages
- Multi-line messages
- High system load

## Root cause

Race condition in `tmux.py:send()`:

```python
# Step 2: Send text with -l (literal)
subprocess.run(["tmux", "send-keys", "-t", self.name, "-l", "--", text])
time.sleep(0.3)

# Step 3: Send Enter
subprocess.run(["tmux", "send-keys", "-t", self.name, "Enter"])
```

Possible causes:
1. Claude UI not ready to receive Enter (still processing pasted text)
2. tmux buffer overflow on large messages
3. Terminal encoding issues with certain characters

## Evidence

From tmux capture:
```
❯ [Pasted 3 lines]
```
or
```
❯ actual message text here
```

Instead of:
```
❯
```
(empty input after successful send)

## Impact

- User message not delivered to Claude
- User thinks message was sent but gets no response
- Must manually attach to tmux and press Enter

## Proposed solution

Add "stuck message recovery" to permission_poller:

1. Extract input line text from screen (after `❯`)
2. Check if it matches:
   - `[Pasted X lines]` pattern
   - OR `thread.last_sent_message` (already tracked)
3. If match found twice in a row (debounce) → send Enter

See: `docs/designs/2026-01-17-stuck-message-recovery.md`

## Affected code

- `src/codogram/tmux.py:26-86` - `TmuxSession.send()`
- `src/codogram/permission_poller.py` - polling loop
- `src/codogram/session_manager.py:104` - `last_sent_message` field

## Workaround

User can:
1. Attach to tmux: `tmux attach -t <session>`
2. Press Enter manually
3. Detach: Ctrl+B, D
