# Restore /start Command Design Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the original /start design where the command works without arguments, auto-determines project/path, shows status for active sessions, and provides interactive directory creation flow.

**Architecture:** The /start command becomes a state machine: detect project from chat → check active session (show status) → resolve path (auto or saved) → check directory exists → interactive flow if not → launch Claude.

**Tech Stack:** Python asyncio, aiogram, existing project_launcher.py and start_flow.py modules.

**Reference:** `docs/designs/2025-12-25-start-claude-from-telegram.md`

---

## Current State

The building blocks exist but are disconnected:
- `project_launcher.py`: resolve_project_path, create_project_directory, git_*, create_tmux_with_claude
- `start_flow.py`: dir_not_found_keyboard, git_setup_keyboard, git_visibility_keyboard
- `bot.py`: callback handlers for start:* exist but /start requires explicit args

**Problem:** `/start` was rewritten to require `<project_name> <cwd>` instead of auto-detection.

---

## Task 1: Add get_project_for_chat helper

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add helper function after get_session_for_chat**

```python
# Add after get_session_for_chat() function (around line 53)

def get_project_for_chat(chat_id: int) -> tuple[str | None, ProjectState | None]:
    """Get project name and state for chat.

    Returns:
        (project_name, project_state) - project_state may be None if not yet created
    """
    # Check if chat already has a project
    project = project_manager.get_by_chat(chat_id)
    if project:
        return project.project_name, project

    # No project found for this chat
    return None, None
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): add get_project_for_chat helper

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add is_claude_running helper

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add helper function**

```python
# Add after get_project_for_chat()

def is_claude_running(project: ProjectState) -> bool:
    """Check if Claude is running for project.

    Returns True if:
    - tmux session exists
    - poller_task is running (not None and not done)
    """
    if not project or not project.tmux_session:
        return False

    # Check tmux exists
    if not is_tmux_session_exists(project.tmux_session):
        return False

    # Check poller is running
    if not project.poller_task or project.poller_task.done():
        return False

    return True
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): add is_claude_running helper

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Add show_status helper

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add helper function**

```python
# Add after is_claude_running()

async def show_status(message: Message, project: ProjectState):
    """Show status of active Claude session."""
    status_lines = [
        f"**Claude активен**",
        f"",
        f"Проект: `{project.project_name}`",
        f"Путь: `{project.cwd}`",
        f"Tmux: `{project.tmux_session}`",
    ]

    if project.session_id:
        status_lines.append(f"Session: `{project.session_id[:8]}...`")

    status_lines.extend([
        "",
        f"Подключиться: `tmux attach -t {project.tmux_session}`",
    ])

    await message.answer("\n".join(status_lines), parse_mode="Markdown")
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): add show_status helper

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add ask_project_name_keyboard

**Files:**
- Modify: `src/telegram_bridge/start_flow.py`

**Step 1: Add keyboard for asking project name**

```python
# Add at end of start_flow.py

def ask_project_name_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown when project name cannot be determined."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отмена", callback_data="start:cancel"),
        ]
    ])
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/start_flow.py
git commit -m "feat(telegram-bridge): add ask_project_name_keyboard

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Rewrite cmd_start to auto-detect

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Replace cmd_start function**

```python
@router.message(Command("start"))
async def cmd_start(message: Message):
    """Start command - auto-detect project or show status."""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    args = message.text.split()[1:]  # Skip /start

    # Case 1: Explicit args provided (backwards compat)
    if len(args) >= 2:
        await _start_with_explicit_args(message, args[0], args[1])
        return

    # Case 2: Single arg = project name
    if len(args) == 1:
        project_name = args[0]
        project = project_manager.get_or_create(project_name)
        project.chat_id = chat_id
        await _start_project_flow(message, project)
        return

    # Case 3: No args - auto-detect from chat
    project_name, project = get_project_for_chat(chat_id)

    if project and is_claude_running(project):
        # Active session - show status
        await show_status(message, project)
        return

    if project_name:
        # Known project - continue flow
        await _start_project_flow(message, project or project_manager.get_or_create(project_name))
        return

    # Unknown chat - ask for project name
    _start_state[chat_id] = {"state": "awaiting_project_name"}
    await message.answer(
        "Отправь имя проекта (например: `my-project`):",
        parse_mode="Markdown",
    )
```

**Step 2: Add _start_with_explicit_args helper (old behavior)**

```python
async def _start_with_explicit_args(message: Message, project_name: str, cwd: str):
    """Handle /start with explicit project_name and cwd (backwards compat)."""
    import asyncio

    chat_id = message.chat.id
    project = project_manager.get_or_create(project_name)
    project.chat_id = chat_id
    project.cwd = cwd

    # Discover tmux
    from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
    tmux_list = find_all_tmux_by_cwd(cwd)

    if len(tmux_list) == 0:
        tmux_by_convention = find_tmux_by_convention(project_name)
        if tmux_by_convention:
            project.tmux_session = tmux_by_convention
            await message.answer(f"Found tmux by convention: {tmux_by_convention}")
        else:
            await message.answer(f"⚠️ No tmux session found for {cwd}")
    elif len(tmux_list) == 1:
        project.tmux_session = tmux_list[0]
        await message.answer(f"Connected to tmux: {tmux_list[0]}")
    else:
        keyboard = create_tmux_selection_keyboard(tmux_list, project_name)
        await message.answer(
            f"Multiple tmux sessions found for {cwd}:\n\nSelect:",
            reply_markup=keyboard
        )
        project_manager._save()
        return

    # Discover session
    project_manager.refresh_project_session(project)
    if project.session_id:
        await message.answer(f"Found session: {project.session_id[:8]}...")
    else:
        await message.answer("No active Claude session (will auto-discover)")

    # Start tasks
    bot = message.bot
    async def start_poller(p: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p)

    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): rewrite cmd_start with auto-detection

- /start without args: auto-detect from chat
- /start <project>: start with project name
- /start <project> <cwd>: explicit mode (backwards compat)
- Shows status if Claude already running

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Add _start_project_flow helper

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add the main flow logic**

```python
async def _start_project_flow(message: Message, project: ProjectState):
    """Main flow: resolve path → check exists → launch or ask."""
    chat_id = message.chat.id
    project.chat_id = chat_id

    # Resolve path: saved cwd or convention ~/dev/{project_name}
    if project.cwd:
        path = project.cwd
        exists = Path(path).is_dir()
    else:
        path_result = resolve_project_path(project.project_name, None)
        path = path_result.path
        exists = path_result.exists

    if exists:
        # Directory exists - discover tmux and launch/connect
        project.cwd = path
        await _connect_or_launch(message, project)
    else:
        # Directory doesn't exist - ask what to do
        _start_state[chat_id] = {
            "state": "awaiting_dir_choice",
            "project": project.project_name,
            "path": path,
        }
        await message.answer(
            f"Директория `{path}` не найдена.\n\nЧто делать?",
            reply_markup=dir_not_found_keyboard(),
            parse_mode="Markdown",
        )

    project_manager._save()
```

**Step 2: Add _connect_or_launch helper**

```python
async def _connect_or_launch(message: Message, project: ProjectState):
    """Connect to existing tmux or offer to launch new Claude session."""
    import asyncio

    chat_id = message.chat.id
    cwd = project.cwd

    # Discover tmux
    from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
    tmux_list = find_all_tmux_by_cwd(cwd)

    if len(tmux_list) == 0:
        # No tmux found - check by convention
        tmux_by_convention = find_tmux_by_convention(project.project_name)
        if tmux_by_convention:
            project.tmux_session = tmux_by_convention
            await message.answer(f"Connected to tmux: {tmux_by_convention}")
        else:
            # No tmux at all - offer to create
            _start_state[chat_id] = {
                "state": "awaiting_launch_confirm",
                "project": project.project_name,
                "path": cwd,
            }
            await message.answer(
                f"Claude не запущен в `{cwd}`.\n\nЗапустить?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Да, запустить", callback_data="start:launch_claude"),
                        InlineKeyboardButton(text="Нет", callback_data="start:cancel"),
                    ]
                ]),
                parse_mode="Markdown",
            )
            return
    elif len(tmux_list) == 1:
        project.tmux_session = tmux_list[0]
        await message.answer(f"Connected to tmux: {tmux_list[0]}")
    else:
        # Multiple - let user choose
        keyboard = create_tmux_selection_keyboard(tmux_list, project.project_name)
        await message.answer(
            f"Multiple tmux sessions found:\n\nSelect:",
            reply_markup=keyboard
        )
        project_manager._save()
        return

    # Discover session and start tasks
    project_manager.refresh_project_session(project)

    bot = message.bot
    async def start_poller(p: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p)

    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    if project.session_id:
        await message.answer(f"✅ Подключено! Session: {project.session_id[:8]}...")
    else:
        await message.answer("✅ Подключено! Ожидаю Claude сессию...")
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): add _start_project_flow and _connect_or_launch

- Auto-resolve path from convention or saved
- Offer to launch if no tmux found
- Multiple tmux selection support

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add launch_claude callback handler

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add callback handler**

```python
@router.callback_query(F.data == "start:launch_claude")
async def on_start_launch_claude(callback: CallbackQuery):
    """Handle launch Claude button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла, начни заново с /start")
        return

    await callback.message.edit_text("Запускаю Claude...")

    project = project_manager.get_or_create(state["project"])
    project.chat_id = chat_id
    project.cwd = state["path"]

    # Define task starters
    bot = callback.bot
    async def start_poller(p: ProjectState):
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState):
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p)

    await launch_claude_new(callback.message, project, start_poller, start_watcher)

    _start_state.pop(chat_id, None)
    await callback.answer()
```

**Step 2: Add cancel callback handler**

```python
@router.callback_query(F.data == "start:cancel")
async def on_start_cancel(callback: CallbackQuery):
    """Handle cancel button."""
    chat_id = callback.message.chat.id
    _start_state.pop(chat_id, None)
    await callback.message.edit_text("Отменено.")
    await callback.answer()
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): add launch_claude and cancel callbacks

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Handle awaiting_project_name state

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add handling in on_message**

In the `on_message` function, add handling for `awaiting_project_name` state:

```python
# In on_message(), after checking state, add this case:

if state["state"] == "awaiting_project_name":
    # User sent project name
    project_name = message.text.strip()
    if not project_name or " " in project_name:
        await message.answer("Имя проекта не может содержать пробелы.")
        return

    project = project_manager.get_or_create(project_name)
    project.chat_id = chat_id

    _start_state.pop(chat_id, None)
    await _start_project_flow(message, project)
    return
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): handle project name input in /start flow

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Add import for InlineKeyboardMarkup

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Update imports**

Add `InlineKeyboardMarkup` and `InlineKeyboardButton` to imports at top of file:

```python
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "fix(telegram-bridge): add missing imports

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Integration testing

**Files:**
- Manual testing

**Step 1: Run tests**

```bash
cd /home/superbereza/dev/personal-agent/agent-tools/telegram-bridge
source venv/bin/activate
python -m pytest tests/ -v
```

Expected: All tests pass

**Step 2: Manual testing scenarios**

1. **Known project with active session:**
   - Send `/start` in a chat that already has an active Claude session
   - Expected: Shows status with project name, path, tmux, session

2. **Known project without active session:**
   - Send `/start` in a chat that has a project but Claude not running
   - Expected: Offers to launch or connect

3. **Unknown chat:**
   - Send `/start` in a new chat
   - Expected: Asks for project name

4. **With project name:**
   - Send `/start myproject`
   - Expected: Resolves path, offers to create if not exists

5. **Explicit args (backwards compat):**
   - Send `/start myproject /path/to/dir`
   - Expected: Works as before

**Step 3: Commit test results if needed**

---

## Task 11: Update design document status

**Files:**
- Modify: `docs/designs/2025-12-25-start-claude-from-telegram.md`

**Step 1: Update status**

Change line 3 from:
```markdown
**Status:** Implemented
```

To:
```markdown
**Status:** Restored (2025-12-26)
```

**Step 2: Commit**

```bash
git add docs/designs/2025-12-25-start-claude-from-telegram.md
git commit -m "docs(telegram-bridge): mark start design as restored

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Task | Description | Key Changes |
|------|-------------|-------------|
| 1 | get_project_for_chat | Helper to find project by chat_id |
| 2 | is_claude_running | Check if Claude active (tmux + poller) |
| 3 | show_status | Display status for active session |
| 4 | ask_project_name_keyboard | Keyboard when project unknown |
| 5 | Rewrite cmd_start | Auto-detect, show status, or start flow |
| 6 | _start_project_flow | Main flow: resolve → check → launch |
| 7 | launch_claude callback | Handle "Да, запустить" button |
| 8 | awaiting_project_name | Handle text input for project name |
| 9 | Fix imports | Add InlineKeyboardMarkup import |
| 10 | Integration testing | Manual test all scenarios |
| 11 | Update design doc | Mark as restored |

**Key design points restored:**
- ✅ `/start` without args (auto-detect)
- ✅ Show status for active sessions
- ✅ Auto-resolve path from `~/dev/{project_name}`
- ✅ Interactive flow when directory doesn't exist
- ✅ Git setup flow (already in callbacks)
- ✅ Backwards compatibility with explicit args
