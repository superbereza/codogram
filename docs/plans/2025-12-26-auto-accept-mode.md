# Auto-Accept Mode Implementation Plan

> **For Claude:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically respond to Claude permission prompts without manual user interaction, with per-thread/per-project settings.

**Design:** See `docs/designs/auto-accept-mode.md`

**Updated:** 2026-01-03

---

### Task 1: Create auto_accept module with select_option

**Files:**
- Create: `src/codogram/auto_accept.py`
- Create: `tests/test_auto_accept.py`

**Step 1: Write failing tests**

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

**Step 2: Run tests to verify they fail**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/test_auto_accept.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'codogram.auto_accept'"

**Step 3: Write implementation**

```python
# src/codogram/auto_accept.py
"""Auto-accept mode for permission prompts."""
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

    return None
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/test_auto_accept.py -v
```

**Step 5: Commit**

```bash
git add src/codogram/auto_accept.py tests/test_auto_accept.py
git commit -m "feat(auto-accept): add select_option function"
```

---

### Task 2: Add auto_accept field to ThreadInfo and ProjectState

**Files:**
- Modify: `src/codogram/session_manager.py`

**Step 1: Read current dataclasses**

Find `ThreadInfo` and `ProjectState` dataclasses in session_manager.py.

**Step 2: Add auto_accept field**

Add to both dataclasses:
```python
auto_accept: bool = False
```

**Step 3: Update serialization (if needed)**

Ensure `to_dict()` and `from_dict()` handle the new field with default:
```python
auto_accept = data.get("auto_accept", False)
```

**Step 4: Run existing tests**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/ -v
```

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(auto-accept): add auto_accept field to ThreadInfo and ProjectState"
```

---

### Task 3: Integrate auto-accept into permission_poller_for_project

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Add import**

```python
from .auto_accept import select_option
```

**Step 2: Find integration point**

In `permission_poller_for_project()`, find the block:
```python
if elapsed >= DEBOUNCE_TIME:
```

**Step 3: Add auto-accept logic before manual path**

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
                thread_id=None,
                messages=[{"text": f"🤖 Auto: {body_preview}"}],
            )
            await telegram_queue.enqueue_nowait(batch)

            tmux.send_key(selected)
            state = PollerState.IDLE
            last_options = None
            continue

    # MANUAL PATH (existing code)...
```

**Step 4: Run tests**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/ -v
```

**Step 5: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "feat(auto-accept): integrate into permission_poller_for_project"
```

---

### Task 4: Integrate auto-accept into permission_poller_for_thread

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Find integration point**

In `permission_poller_for_thread()`, find the block:
```python
if elapsed >= DEBOUNCE_TIME:
```

**Step 2: Add auto-accept logic**

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
                thread_id=thread_id,
                messages=[{"text": f"🤖 Auto: {body_preview}"}],
            )
            await telegram_queue.enqueue_nowait(batch)

            tmux.send_key(selected)
            state = PollerState.IDLE
            last_options = None
            continue

    # MANUAL PATH (existing code)...
```

**Step 3: Run tests**

```bash
cd /home/superbereza/dev/codogram && PYTHONPATH=src pytest tests/ -v
```

**Step 4: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "feat(auto-accept): integrate into permission_poller_for_thread"
```

---

### Task 5: Add /auto_accept command

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Add command handler**

```python
@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept: /auto_accept on|off"""
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

    args = (message.text or "").split()[1:]

    if not args:
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

**Step 2: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(auto-accept): add /auto_accept command"
```

---

### Task 6: Add /settings command

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

### Task 7: Add commands to bot menu

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

### Task 8: Update ROADMAP

**Files:**
- Modify: `docs/ROADMAP.md`

**Step 1: Move auto-accept from Backlog to Done**

Move the "Auto-accept mode" section.

**Step 2: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs: mark auto-accept mode as done"
```

---

### Task 9: Manual integration test

**No code changes - manual testing only**

**Checklist:**

1. [ ] Start bot: `./restart.sh`
2. [ ] `/auto_accept` — shows OFF status
3. [ ] `/auto_accept on` — enables
4. [ ] `/settings` — shows "Auto-accept: ⚡ ON"
5. [ ] Trigger permission prompt (ask Claude to create a file)
6. [ ] Verify: "🤖 Auto: ..." notification, no keyboard
7. [ ] `/auto_accept off` — disables
8. [ ] Trigger another prompt
9. [ ] Verify: keyboard shown (manual mode)
10. [ ] Restart bot: `./restart.sh`
11. [ ] `/settings` — setting persisted

---

**Plan complete.** 9 tasks total.
