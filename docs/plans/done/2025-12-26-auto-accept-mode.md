# Auto-Accept Mode Implementation Plan

> **For Claude:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically respond to Claude permission prompts without manual user interaction, with per-thread/per-project settings.

**Design:** See `docs/designs/auto-accept-mode.md`

**Updated:** 2026-01-03

---

### Task 1: Create auto_accept module with select_option and try_auto_accept

**Files:**
- Create: `src/codogram/auto_accept.py`
- Create: `tests/test_auto_accept.py`

**Step 1: Write failing tests for select_option**

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

**Step 2: Write failing tests for try_auto_accept**

```python
# tests/test_auto_accept.py (add to same file)
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
    call_args = queue.enqueue_nowait.call_args[0][0]
    assert "[no details]" in call_args.messages[0]["text"]
```

**Step 3: Run tests to verify they fail**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/test_auto_accept.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'codogram.auto_accept'"

**Step 4: Write implementation**

```python
# src/codogram/auto_accept.py
"""Auto-accept mode for permission prompts."""
import re
from typing import TYPE_CHECKING

from .telegram_queue import OutgoingBatch
from .tmux import TmuxSession
from .logging_config import logger

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue

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

    return None


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

**Step 5: Run tests to verify they pass**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/test_auto_accept.py -v
```

**Step 6: Commit**

```bash
git add src/codogram/auto_accept.py tests/test_auto_accept.py
git commit -m "feat(auto-accept): add select_option and try_auto_accept functions"
```

---

### Task 2: Add auto_accept field to ThreadInfo and ProjectState

**Files:**
- Modify: `src/codogram/session_manager.py`

**Step 1: Read current dataclasses**

Find `ThreadInfo` and `ProjectState` dataclasses in session_manager.py.

**Step 2: Add auto_accept field to both**

```python
# In ThreadInfo:
auto_accept: bool = False

# In ProjectState:
auto_accept: bool = False
```

**Step 3: Update to_dict() methods**

Add to serialization:
```python
"auto_accept": self.auto_accept,
```

**Step 4: Update from_dict() / loading with backwards compat**

```python
auto_accept = data.get("auto_accept", False)
```

**Step 5: Run existing tests**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/ -v
```

**Step 6: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(auto-accept): add auto_accept field to ThreadInfo and ProjectState"
```

---

### Task 3: Integrate auto-accept into both permission pollers

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Add import**

```python
from .auto_accept import try_auto_accept
```

**Step 2: Integrate into permission_poller_for_project()**

Find the block `if elapsed >= DEBOUNCE_TIME:` and add before manual path:

```python
if project.auto_accept:
    if await try_auto_accept(
        parsed.options, parsed.body, tmux,
        telegram_queue, chat_id, None, project.project_name
    ):
        state = PollerState.IDLE
        last_options = None
        continue
```

**Step 3: Integrate into permission_poller_for_thread()**

Same pattern:

```python
if thread.auto_accept:
    if await try_auto_accept(
        parsed.options, parsed.body, tmux,
        telegram_queue, chat_id, thread_id, thread.name
    ):
        state = PollerState.IDLE
        last_options = None
        continue
```

**Step 4: Run tests**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/ -v
```

**Step 5: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "feat(auto-accept): integrate into permission pollers"
```

---

### Task 4: Add /auto_accept command

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Add command handler**

- `/auto_accept` — toggle on/off for current context
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

**Step 2: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(auto-accept): add /auto_accept command"
```

---

### Task 5: Add /settings command

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Add command handler**

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

**Step 2: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(auto-accept): add /settings command"
```

---

### Task 6: Add commands to bot menu

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Find bot commands registration**

Look for `set_my_commands` or commands list.

**Step 2: Add new commands**

```python
BotCommand(command="settings", description="Show current settings"),
BotCommand(command="auto_accept", description="Toggle auto-accept mode"),
```

**Step 3: Restart bot and verify menu**

```bash
./restart.sh
```

**Step 4: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(auto-accept): add commands to bot menu"
```

---

### Task 7: Update ROADMAP

**Files:**
- Modify: `docs/ROADMAP.md`

**Step 1: Move auto-accept from Backlog to Done**

Move the "Auto-accept mode" section with updated description.

**Step 2: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs: mark auto-accept mode as done"
```

---

### Task 8: Manual integration test

**No code changes - manual testing only**

**Checklist:**

1. [ ] Start bot: `./restart.sh`
2. [ ] `/help` — shows all commands including auto-accept
3. [ ] `/auto_accept` — toggles ON (first call)
4. [ ] `/settings` — shows "Auto-accept: ⚡ ON"
5. [ ] Trigger permission prompt (ask Claude to create a file)
6. [ ] Verify: "🤖 Auto: ..." notification, no keyboard
7. [ ] Verify: log shows "auto_accept <context> option=1"
8. [ ] `/auto_accept` — toggles OFF (second call)
9. [ ] Trigger another prompt
10. [ ] Verify: keyboard shown (manual mode)
11. [ ] `/auto_accept reset all` — resets all to off
12. [ ] Restart bot: `./restart.sh`
13. [ ] `/settings` — setting persisted

---

**Plan complete.** 8 tasks total.

## Refactoring Notes

This implementation is designed for easy migration during bot refactoring:

- `try_auto_accept()` encapsulates all logic — when pollers are unified, only the call site changes
- Functions can be moved to `domain/` and `services/` directories as-is
- Commands move to `handlers/settings.py` without modification
