# Auto-Suspend & Auto-Resume Design

**Date:** 2026-01-24
**Status:** Draft

## Summary

Two related features:
1. **Auto-suspend:** Kill idle sessions after 12 hours to save RAM
2. **Auto-resume:** Automatically relaunch Claude when user writes to dead/suspended session

## Why

Claude Code processes consume ~100-600MB RAM each. With many sessions running, total RAM usage grows significantly. Auto-suspend kills idle tmux sessions and resumes them on demand.

## Auto-Resume Cases

When user sends message, check in order:

| Condition | Message | Action |
|-----------|---------|--------|
| `suspended=True` | "⏸️ Session was suspended. Resuming..." | Relaunch Claude |
| `!tmux.exists()` | "⚡ Tmux not found. Launching..." | Relaunch Claude |
| `tmux.exists() && !is_claude_ready()` | "💥 Claude not responding. Relaunching..." | Kill tmux, relaunch |

**Note:** Crash detection (`detect_crash()`) may have bugs — investigate separately.

This design supersedes `docs/designs/2026-01-18-auto-resume-design.md`.

## Activity Tracking

### What counts as activity

- User sends message to Claude
- Commands: `/start`, `/resume`, `/clear_context`, `/clear`, `/new`, `/esc`, `/shift_tab`

### How it's tracked

```python
# ThreadInfo gets new field
last_activity_at: float | None = None  # Persisted

# Effective activity = max(last_activity_at, jsonl_mtime)
# jsonl_mtime catches Claude-side activity (tool calls, etc.)
```

### Update points

- `message_router.route_message()` — message sent to Claude
- `sessions.cmd_clear_context()` — `/clear`, `/new`, `/clear_context`
- `sessions.cmd_esc()` — `/esc`
- `/shift_tab` handler

## Suspend Flow

Coordinator checks every 15 seconds:

```python
async def _check_suspend_timeout(self, project: ProjectInfo):
    for thread in project.threads.values():
        if not thread.session_id or thread.suspended:
            continue
        if not self._is_tmux_alive(project.tmux_session):
            continue

        jsonl_mtime = self._get_jsonl_mtime(thread.jsonl_path)
        last_activity = thread.last_activity_at or 0
        idle_seconds = time.time() - max(last_activity, jsonl_mtime or 0)

        if idle_seconds > SUSPEND_TIMEOUT_HOURS * 3600:
            self._kill_tmux(project.tmux_session)
            thread.suspended = True
            self.session_manager.save()
            log.info(f"suspended: {project.name}, idle {idle_seconds/3600:.1f}h")
```

**Silent suspend** — no Telegram notification when suspending.

## Resume Flow

When user writes to dead/suspended thread:

```python
async def route_message(self, message, thread, project):
    # Determine resume reason
    resume_reason = None
    if thread.suspended:
        resume_reason = "suspended"
    elif not tmux.exists():
        resume_reason = "tmux_missing"
    elif not tmux.is_claude_ready():
        resume_reason = "claude_dead"

    if resume_reason:
        # 1. Store pending action
        if message.text.startswith("/"):
            thread.pending_action = PendingAction("command", message.text)
        else:
            thread.pending_action = PendingAction("message", message.text)

        # 2. Notify user (different message per reason)
        await bot.send(RESUME_MESSAGES[resume_reason])

        # 3. Kill tmux if exists but Claude dead
        if resume_reason == "claude_dead":
            tmux.kill()

        # 4. Resume (creates tmux, runs claude --resume, shows animation)
        thread.resuming = True
        await resume_service.resume(project, thread)
        thread.resuming = False
        thread.suspended = False

        # 5. After Claude ready — handle pending action
        if action.type == "command":
            await bot.send("Please send your command again.")
        else:
            await bot.send("Processing your message...")
            await self._send_to_claude(project, action.text)

        thread.pending_action = None
        return
```

## Data Model

### New ThreadInfo fields

| Field | Type | Persisted | Purpose |
|-------|------|-----------|---------|
| `last_activity_at` | `float \| None` | Yes | Last user interaction timestamp |
| `suspended` | `bool` | Yes | Session is suspended |
| `resuming` | `bool` | No | Resume in progress |
| `pending_action` | `PendingAction \| None` | No | Held action during resume |

### PendingAction

```python
@dataclass
class PendingAction:
    type: Literal["message", "command"]
    text: str
```

## Configuration

```python
# src/codogram/config.py
SUSPEND_TIMEOUT_HOURS = 12
```

Resume uses existing launch animation timeout.

## Error Handling

| Situation | Action |
|-----------|--------|
| Tmux fails to create | "Failed to resume. Try /start again." |
| Claude doesn't start | Timeout → "Claude didn't start. Try /start again." |
| jsonl not found | Resume without `--resume` (new session) |

### Race conditions

**User writes during resume:**
```python
if thread.resuming:
    await bot.send("Session is resuming, please wait...")
    return
```

**Multiple threads suspended:**
- Each thread has its own tmux session
- Resume independently

## Messages

| When | Message |
|------|---------|
| Suspended session | "⏸️ Session was suspended. Resuming..." |
| Tmux missing | "⚡ Tmux not found. Launching..." |
| Claude dead | "💥 Claude not responding. Relaunching..." |
| After resume (command) | "Please send your command again." |
| After resume (message) | "Processing your message..." |
| During resume (new msg) | "Session is resuming, please wait..." |

## Affected Files

- `src/codogram/core/coordinator.py` — suspend check in loop
- `src/codogram/services/message_router.py` — resume flow
- `src/codogram/domain/models.py` — ThreadInfo fields, PendingAction
- `src/codogram/core/session_manager.py` — persist new fields
- `src/codogram/handlers/sessions.py` — update activity
- `src/codogram/config.py` — SUSPEND_TIMEOUT_HOURS
- `src/codogram/strings.py` — new messages

## Cleanup

Delete old design after implementation:
- `docs/designs/2026-01-18-auto-resume-design.md`
