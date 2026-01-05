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

## Core Logic

### select_option()

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

### try_auto_accept()

Unified function for both pollers — **no code duplication**:

```python
# src/codogram/auto_accept.py
from typing import TYPE_CHECKING

from .telegram_queue import OutgoingBatch
from .tmux import TmuxSession
from .logging_config import logger

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue

async def try_auto_accept(
    options: list[str],
    body: str | None,
    tmux: TmuxSession,
    telegram_queue: "TelegramQueue",
    chat_id: int,
    thread_id: int | None,
    context_name: str,
) -> bool:
    """Try to auto-accept a permission prompt.

    Returns True if auto-accepted, False if manual mode needed.

    Args:
        options: List of permission options from screen
        body: Permission prompt body text
        tmux: TmuxSession for sending keys
        telegram_queue: Queue for sending notifications
        chat_id: Telegram chat ID
        thread_id: Telegram thread ID (None for simple mode)
        context_name: For logging (project name or thread name)
    """
    selected = select_option(options)
    if selected is None:
        return False

    body_preview = (body[:80] + "...") if body else "[no details]"
    logger.info(f"auto_accept {context_name} option={selected}")

    batch = OutgoingBatch(
        chat_id=chat_id,
        thread_id=thread_id,
        messages=[{"text": f"🤖 Auto: {body_preview}"}],
    )
    await telegram_queue.enqueue_nowait(batch)

    tmux.send_key(selected)
    return True
```

**Benefits:**
- Single source of truth (DRY)
- Easy to test with mocked tmux/queue
- Minimal changes needed when refactoring pollers
- Handles empty body gracefully (`"[no details]"`)

## Permission Poller Integration

### For `permission_poller_for_project()`

```python
from .auto_accept import try_auto_accept

# Inside DEBOUNCING state, after elapsed >= DEBOUNCE_TIME:
if project.auto_accept:
    if await try_auto_accept(
        parsed.options, parsed.body, tmux,
        telegram_queue, chat_id, None, project.project_name
    ):
        state = PollerState.IDLE
        last_options = None
        continue

# MANUAL PATH (existing code)...
```

### For `permission_poller_for_thread()`

```python
# Inside DEBOUNCING state, after elapsed >= DEBOUNCE_TIME:
if thread.auto_accept:
    if await try_auto_accept(
        parsed.options, parsed.body, tmux,
        telegram_queue, chat_id, thread_id, thread.name
    ):
        state = PollerState.IDLE
        last_options = None
        continue

# MANUAL PATH (existing code)...
```

**Result:** 5 lines per poller instead of 25 lines.

## User Commands

### /auto_accept

Toggle auto-accept in current context:

- `/auto_accept` — toggle on/off for current context (thread or project)
- `/auto_accept reset all` — reset project and all threads to off

```python
@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept or reset all."""
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
        thread = project.threads.get(thread_id)

    args = (message.text or "").split()[1:]

    # /auto_accept reset all - reset all to off
    if len(args) >= 2 and args[0].lower() == "reset" and args[1].lower() == "all":
        project.auto_accept = False
        if project.threads:
            for t in project.threads.values():
                t.auto_accept = False
        project_manager._save()
        await message.answer("Auto-accept reset to **OFF** for project and all threads.", parse_mode="Markdown")
        return

    # /auto_accept - toggle current context
    if thread:
        thread.auto_accept = not thread.auto_accept
        status = "⚡ ON" if thread.auto_accept else "OFF"
        await message.answer(f"Auto-accept for `{thread.name}`: **{status}**", parse_mode="Markdown")
    else:
        project.auto_accept = not project.auto_accept
        status = "⚡ ON" if project.auto_accept else "OFF"
        await message.answer(f"Auto-accept: **{status}**", parse_mode="Markdown")
    project_manager._save()
```

### /help

Show available commands (includes auto-accept section).

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

### Unit Tests for select_option()

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

### Integration Tests for try_auto_accept()

```python
# tests/test_auto_accept.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from codogram.auto_accept import try_auto_accept

@pytest.mark.asyncio
async def test_try_auto_accept_success():
    """Auto-accept returns True and sends notification."""
    tmux = MagicMock()
    queue = AsyncMock()

    result = await try_auto_accept(
        options=["1. Yes", "2. No"],
        body="Run command: git status",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test-project",
    )

    assert result is True
    tmux.send_key.assert_called_once_with("1")
    queue.enqueue_nowait.assert_called_once()

@pytest.mark.asyncio
async def test_try_auto_accept_no_safe_option():
    """Returns False when no safe option available."""
    tmux = MagicMock()
    queue = AsyncMock()

    result = await try_auto_accept(
        options=["1. Allow for session", "2. No"],
        body="Some prompt",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test-project",
    )

    assert result is False
    tmux.send_key.assert_not_called()
    queue.enqueue_nowait.assert_not_called()

@pytest.mark.asyncio
async def test_try_auto_accept_empty_body():
    """Handles empty body gracefully."""
    tmux = MagicMock()
    queue = AsyncMock()

    result = await try_auto_accept(
        options=["1. Yes"],
        body=None,
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=456,
        context_name="test-thread",
    )

    assert result is True
    # Check notification contains "[no details]"
    call_args = queue.enqueue_nowait.call_args[0][0]
    assert "[no details]" in call_args.messages[0]["text"]
```

### Manual Testing Checklist

- [ ] `/auto_accept` — toggles on (first call)
- [ ] `/auto_accept` — toggles off (second call)
- [ ] `/auto_accept reset all` — resets project and all threads to off
- [ ] `/settings` — shows auto-accept status
- [ ] `/help` — shows all commands including auto-accept
- [ ] Prompt with "Yes" — auto-accepted, notification in chat
- [ ] Prompt with "Allow for session" — NOT auto-accepted, keyboard shown
- [ ] Choice question — keyboard (manual)
- [ ] Bot restart — setting persisted

## Refactoring Compatibility

This design is compatible with planned refactoring (see `docs/designs/2025-12-27-bot-refactoring/`):

| Component | Current Location | Future Location | Migration Effort |
|-----------|-----------------|-----------------|------------------|
| `select_option()` | `auto_accept.py` | `domain/auto_accept.py` | Move file |
| `try_auto_accept()` | `auto_accept.py` | `services/auto_accept.py` | Move file |
| `/auto_accept` cmd | `bot.py` | `handlers/settings.py` | Move function |
| `/settings` cmd | `bot.py` | `handlers/settings.py` | Move function |
| Data model | `session_manager.py` | `domain/models.py` | Already compatible |

**Key benefit:** `try_auto_accept()` encapsulates all integration logic. When pollers are unified in Phase 11, only the call site changes — the function stays the same.

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

- [ ] Create `auto_accept.py` with `select_option()` and `try_auto_accept()`
- [ ] Add `auto_accept: bool = False` to `ThreadInfo`
- [ ] Add `auto_accept: bool = False` to `ProjectState`
- [ ] Update load/save for backwards compat
- [ ] Integrate into both pollers (5 lines each)
- [ ] Add `/auto_accept` command
- [ ] Add `/settings` command
- [ ] Add commands to bot menu
- [ ] Write unit and integration tests
- [ ] Manual testing
- [ ] Update ROADMAP (Backlog -> Done)

---

**Design complete.** Ready for implementation.
