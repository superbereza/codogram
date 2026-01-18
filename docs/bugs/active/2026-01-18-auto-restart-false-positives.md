# Bug: Auto-restart Claude causes false positives and spam

**Date:** 2026-01-18
**Severity:** Medium (feature disabled)
**Status:** Active - needs redesign

## Summary

Attempted to implement auto-restart when Claude exits. Implementation caused false positives and spam messages every 60 seconds.

## What was implemented

### 1. Exit detection function (`permission_poller.py`)

```python
def _detect_exit(screen: str) -> bool:
    """Detect if Claude exited normally (no crash)."""
    if is_claude_ready(screen):
        return False

    lines = screen.split("\n")
    last_lines = "\n".join(lines[-15:])

    # Must have shell prompt
    has_shell = any(p in last_lines for p in SHELL_PROMPTS)
    if not has_shell:
        return False

    # Must NOT have crash signatures
    for sig in CRASH_SIGNATURES:
        if sig in last_lines:
            return False

    return True
```

### 2. Auto-restart logic in poller main loop

```python
if _detect_exit(screen):
    now = time.time()
    if now - last_restart_time >= RESTART_COOLDOWN:  # 60 sec
        logger.info(f"{log_prefix}: Claude exited, auto-restarting...")
        last_restart_time = now

        session_id = thread.session_id if thread else project.session_id
        cmd = f"claude --resume {session_id}" if session_id else "claude"
        tmux.send(cmd)

        # Notify user
        await telegram_queue.enqueue_nowait(OutgoingBatch(...))
```

### 3. New string added (`strings.py`)

```python
CLAUDE_AUTO_RESTARTED = f"{STATUS_INFO} Claude exited, auto\\-restarting\\.\\.\\."
```

## Problems encountered

### Problem 1: False positive detection

`SHELL_PROMPTS` includes `❯ ` which appears in both:
- Shell prompt: `➜ project git:(main) ❯`
- Claude input: `❯ ` (empty input line)

`is_claude_ready()` should filter this out by checking for two `───` lines, but failed in some states.

### Problem 2: Command sent to wrong place

When false positive triggers while Claude IS running:
- `tmux.send("claude --resume ...")` goes to Claude's input line
- Claude receives it as a message, not shell command
- This corrupts the session

### Problem 3: Spam loop

Once triggered:
1. False positive detects "exit"
2. Sends `claude --resume` to Claude's input
3. Waits 60 sec cooldown
4. False positive triggers again
5. Repeat → spam every 60 seconds

**Evidence from logs:**
```
09:23:55 [INFO] Thread poller [set-up-flow-redesign]: Claude exited, auto-restarting...
09:24:56 [INFO] Thread poller [set-up-flow-redesign]: Claude exited, auto-restarting...
09:26:10 [INFO] Thread poller [set-up-flow-redesign]: Claude exited, auto-restarting...
... (every ~60 seconds)
```

## Current state of code

### Disabled (commented out)

In `permission_poller.py` around line 342:
```python
# Exit detection + auto-restart
# NOTE: Temporarily disabled - false positives when Claude is running
# See: docs/bugs/active/2026-01-18-auto-restart-false-positives.md
# if _detect_exit(screen):
#     ...
```

### Left in code but unused

- `_detect_exit()` function (line ~77)
- `RESTART_COOLDOWN` constant
- `last_restart_time` state variable
- `import time`
- `strings.CLAUDE_AUTO_RESTARTED`

## Proposed fix

Instead of screen parsing, use process-based detection:

### 1. Add `TmuxSession.is_claude_running()`

```python
def is_claude_running(self) -> bool:
    """Check if Claude process is running in this tmux pane."""
    result = subprocess.run(
        ["tmux", "list-panes", "-t", self.name, "-F", "#{pane_current_command}"],
        capture_output=True, text=True
    )
    cmd = result.stdout.strip()
    return cmd in ("claude", "node")  # Claude is Node.js based
```

### 2. Use in `history_watcher.py` health check

Extend existing tmux health check:

```python
# Current (detects tmux death):
if thread.session_id and not tmux.exists():
    # tmux session died entirely

# Add (detects Claude exit within tmux):
if thread.session_id and tmux.exists() and not tmux.is_claude_running():
    # tmux exists but Claude exited → notify or auto-restart
```

### 3. Action options

A. **Notify only** — safest, let user /start manually
B. **Auto-restart** — now safe because we're definitely in shell

## Why process-based is better

| Approach | Pros | Cons |
|----------|------|------|
| Screen parsing | No extra calls | `❯` ambiguity, false positives |
| Process check | Direct answer, no ambiguity | One subprocess call |

## Related

- `history_watcher.py` already has health check for tmux death
- `/restart` command flow in `handlers/start.py`
- Crash detection in `permission_poller.py` (works, different issue)
