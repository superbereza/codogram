# Auto-Accept Mode Design

**Status:** Updated
**Created:** 2025-12-26
**Updated:** 2026-01-03
**Feature:** Automatic permission prompt acceptance for codogram

## Overview

Auto-accept automatically responds to Claude permission prompts without manual user interaction. Setting is **per-thread** for forum mode and **per-project** for simple mode.

All admins see the same setting — if a thread is "trusted", it's trusted for everyone.

## Data Model

### ThreadInfo (forum mode)

```python
@dataclass
class ThreadInfo:
    thread_id: int
    name: str
    session_id: str | None = None
    # ... existing fields ...
    auto_accept: bool = False  # NEW
```

### ProjectState (simple mode)

```python
@dataclass
class ProjectState:
    project_name: str
    chat_id: int
    # ... existing fields ...
    auto_accept: bool = False  # NEW
```

### config.json

Persisted automatically through existing `_save()` methods:

```json
{
  "projects": {
    "codogram": {
      "chat_id": -1001234567890,
      "auto_accept": false,
      "threads": {
        "123": {
          "name": "main",
          "auto_accept": true
        }
      }
    }
  }
}
```

### Backwards Compatibility

When loading old configs without `auto_accept` field:

```python
auto_accept = data.get("auto_accept", False)
```

## Detection Logic

### Option Selection

Select **single-action** option, skip session-wide:

```python
# src/codogram/auto_accept.py
import re

AUTO_ACCEPT_PHRASES = ["yes", "allow"]

def select_option(options: list[str]) -> str | None:
    """Select safe option for auto-accept.

    Returns option number ("1", "2") or None if no safe option.
    Skips session-wide permissions ("all", "session").
    """
    if not options:
        return None

    for option in options:
        option_lower = option.lower()

        # Skip session-wide (too permissive)
        if "session" in option_lower or "all" in option_lower:
            continue

        if any(phrase in option_lower for phrase in AUTO_ACCEPT_PHRASES):
            match = re.match(r'^(\d+)\.', option.strip())
            return match.group(1) if match else None

    return None  # No safe option -> manual mode
```

### Examples

| Options | Result | Reason |
|---------|--------|--------|
| `["1. Yes", "2. Allow all..."]` | `"1"` | Picks "Yes" |
| `["1. Allow for session", "2. No"]` | `None` | Session-wide skipped |
| `["1. src/main.py", "2. Cancel"]` | `None` | Choice question |

## Permission Poller Integration

### For `permission_poller_for_project()` (~line 148)

```python
if elapsed >= DEBOUNCE_TIME:
    # Check auto-accept (project-level for simple mode)
    if project.auto_accept:
        selected = select_option(parsed.options)

        if selected is not None:
            body_preview = (parsed.body[:80] + "...") if parsed.body else ""

            logger.info(f"auto_accept project={project.project_name} option={selected}")

            batch = OutgoingBatch(
                chat_id=chat_id,
                thread_id=None,  # simple mode
                messages=[{"text": f"🤖 Auto: {body_preview}"}],
            )
            await telegram_queue.enqueue_nowait(batch)

            tmux.send_key(selected)
            state = PollerState.IDLE
            last_options = None
            continue

    # MANUAL PATH (existing code)...
```

### For `permission_poller_for_thread()` (~line 328)

```python
if elapsed >= DEBOUNCE_TIME:
    # Check auto-accept (thread-level for forum mode)
    if thread.auto_accept:
        selected = select_option(parsed.options)

        if selected is not None:
            body_preview = (parsed.body[:80] + "...") if parsed.body else ""

            logger.info(f"auto_accept thread={thread.name} option={selected}")

            batch = OutgoingBatch(
                chat_id=chat_id,
                thread_id=thread_id,  # forum topic
                messages=[{"text": f"🤖 Auto: {body_preview}"}],
            )
            await telegram_queue.enqueue_nowait(batch)

            tmux.send_key(selected)
            state = PollerState.IDLE
            last_options = None
            continue

    # MANUAL PATH (existing code)...
```

### Import

```python
from .auto_accept import select_option
```

## User Commands

### /auto_accept

Toggle auto-accept in current context:

```python
@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept: /auto_accept on|off"""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id  # None if not in topic

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project. Use /start first.")
        return

    # Determine target: thread or project
    thread = None
    if thread_id and project.threads:
        thread = project.threads.get(str(thread_id))

    args = (message.text or "").split()[1:]

    if not args:
        # Show status
        enabled = thread.auto_accept if thread else project.auto_accept
        target = f"thread `{thread.name}`" if thread else f"project `{project.project_name}`"
        status = "ON ⚡" if enabled else "OFF"
        await message.answer(f"Auto-accept for {target}: **{status}**", parse_mode="Markdown")
        return

    mode = args[0].lower()
    if mode == "on":
        if thread:
            thread.auto_accept = True
        else:
            project.auto_accept = True
        project_manager.save()
        await message.answer("⚡ Auto-accept **ON**", parse_mode="Markdown")
    elif mode == "off":
        if thread:
            thread.auto_accept = False
        else:
            project.auto_accept = False
        project_manager.save()
        await message.answer("Auto-accept **OFF**", parse_mode="Markdown")
    else:
        await message.answer("Usage: `/auto_accept on|off`", parse_mode="Markdown")
```

### /settings

Show current settings:

```python
@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Show current settings."""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("No project. Use /start first.")
        return

    thread = None
    if thread_id and project.threads:
        thread = project.threads.get(str(thread_id))

    if thread:
        auto_status = "⚡ ON" if thread.auto_accept else "OFF"
        text = (
            f"**Settings** (thread `{thread.name}`)\n\n"
            f"Auto-accept: {auto_status}"
        )
    else:
        auto_status = "⚡ ON" if project.auto_accept else "OFF"
        text = (
            f"**Settings** (`{project.project_name}`)\n\n"
            f"Auto-accept: {auto_status}"
        )

    await message.answer(text, parse_mode="Markdown")
```

### Bot Menu

```python
commands = [
    BotCommand(command="start", description="Start/connect project"),
    BotCommand(command="settings", description="Show current settings"),
    BotCommand(command="auto_accept", description="Toggle auto-accept mode"),
    # ...
]
```

## Testing

### Unit Tests

```python
# tests/test_auto_accept.py

import pytest
from codogram.auto_accept import select_option

def test_select_option_picks_yes():
    assert select_option(["1. Yes", "2. Allow all"]) == "1"

def test_select_option_picks_allow_once():
    assert select_option(["1. Allow once", "2. No"]) == "1"

def test_select_option_skips_session_wide():
    assert select_option(["1. Allow for session", "2. No"]) is None

def test_select_option_skips_all():
    assert select_option(["1. Yes, allow all edits", "2. No"]) is None

def test_select_option_no_match():
    assert select_option(["1. src/main.py"]) is None

def test_select_option_empty():
    assert select_option([]) is None
```

### Manual Testing Checklist

- [ ] `/auto_accept` — shows status
- [ ] `/auto_accept on` — enables
- [ ] `/auto_accept off` — disables
- [ ] `/settings` — shows auto-accept status
- [ ] Prompt with "Yes" — auto-accepted, notification in chat
- [ ] Prompt with "Allow for session" — NOT auto-accepted, keyboard shown
- [ ] Choice question — keyboard (manual)
- [ ] Bot restart — setting persisted

## Implementation Checklist

### Files

| File | Action |
|------|--------|
| `src/codogram/auto_accept.py` | CREATE |
| `src/codogram/session_manager.py` | MODIFY |
| `src/codogram/permission_poller.py` | MODIFY |
| `src/codogram/bot.py` | MODIFY |
| `src/codogram/main.py` | MODIFY |
| `tests/test_auto_accept.py` | CREATE |
| `docs/ROADMAP.md` | MODIFY |

### Tasks

- [ ] Create `auto_accept.py` with `select_option()`
- [ ] Add `auto_accept: bool = False` to `ThreadInfo`
- [ ] Add `auto_accept: bool = False` to `ProjectState`
- [ ] Update load/save for backwards compat
- [ ] Integrate into `permission_poller_for_project()`
- [ ] Integrate into `permission_poller_for_thread()`
- [ ] Add `/auto_accept` command
- [ ] Add `/settings` command
- [ ] Add commands to bot menu
- [ ] Write unit tests
- [ ] Manual testing
- [ ] Update ROADMAP (Backlog -> Done)

---

**Design complete.** Ready for implementation.
