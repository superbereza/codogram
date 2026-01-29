# Command Merge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge /thread and /branch into unified /new_chat command with simplified menu.

**Architecture:** New `handlers/new_chat.py` contains complete flow (context → uncommitted → name → create). Old handlers become pure aliases. All old callbacks dropped.

**Tech Stack:** aiogram, Python 3.11+

**Task Dependencies:**
- Task 1 (strings) → no deps
- Task 2 (menu) → no deps
- Task 3 (new_chat.py) → depends on Task 1
- Task 4 (register router) → depends on Task 3
- Tasks 5-8 (aliases/renames) → depend on Task 4
- Task 9 (remove create_flow) → depends on Task 3
- Task 10 (help) → depends on Task 1
- Task 11 (E2E) → depends on all

---

## Task 1: Add new strings

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add new chat creation strings**

Add at end of file:

```python
# --- New Chat Flow ---

NEW_CHAT_CONTEXT = f"""{STATUS_QUESTION} Creating chat from:
📁 `{{directory}}`
🌿 `{{branch}}`

To branch from main, run /new\\_chat in General"""

NEW_CHAT_CONTEXT_MAIN = f"""{STATUS_QUESTION} Creating chat from:
📁 `{{directory}}`
🌿 `{{branch}}`"""

NEW_CHAT_CHOOSE = "Where to create?"
NEW_CHAT_NAME_PROMPT = "Chat name?\n\nSend name or pick random"
NEW_CHAT_CREATING = f"{STATUS_PENDING} Creating chat `{{name}}`..."
NEW_CHAT_CREATED = f"{STATUS_OK} Chat `{{name}}` created"
NEW_CHAT_ERROR = f"{STATUS_ERR} Error creating chat"

BTN_CREATE_HERE = "Create here"
BTN_CREATE_ISOLATED = "Create isolated"

# Uncommitted changes (reuse existing or add)
NC_UNCOMMITTED = f"{STATUS_WARN} Uncommitted changes detected"
NC_UNCOMMITTED_CLEAN = "Create from last commit"
NC_UNCOMMITTED_COMMIT = "Commit first"

# --- Help ---

HELP_TEXT = """Troubleshoot

If bot isn't responding, try /reset\\_chat — it's safe for context\\.

To wipe project and start fresh: /hard\\_reset\\. 🚨 Dangerous zone\\!

─────────────────

Chats
/new\\_chat — create new chat: topic \\& Claude session
/finish\\_chat — archive chat and stop Claude
/start — connect or resume
/reset\\_chat — restart Claude process

Context
/clear\\_context — clear current Claude context

Operations
/esc — send Esc, stop current operation
/shift\\_tab — cycle Claude approval mode
/auto\\_accept — accept every Claude permission 🚧

Settings
/settings — show settings
/get\\_debug\\_ids — debug info"""
```

**Step 2: Verify syntax**

```bash
python -m py_compile src/codogram/strings.py
```

**Step 3: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat: add strings for /new_chat flow and /help"
```

---

## Task 2: Update services/menu.py

**Files:**
- Modify: `src/codogram/services/menu.py`

**Step 1: Replace _ALL_COMMANDS**

```python
_ALL_COMMANDS = [
    ("esc", "Send Esc, stop current operation", True),
    ("shift_tab", "Cycle Claude approval mode", True),
    ("auto_accept", "Accept every Claude permission 🚧", True),
    ("new_chat", "Create new chat: topic & Claude session", True),
    ("finish_chat", "Archive chat and stop Claude", False),  # forum only
    ("start", "Connect or resume", True),
    ("settings", "Show settings", True),
    ("clear_context", "Clear current Claude context", True),
    ("reset_chat", "Restart Claude process", True),
    ("get_debug_ids", "Debug info", True),
    ("help", "Show help", True),
    ("hard_reset", "Full project reset", True),
]
```

**Step 2: Verify syntax**

```bash
python -m py_compile src/codogram/services/menu.py
```

**Step 3: Commit**

```bash
git add src/codogram/services/menu.py
git commit -m "feat: update menu with new command names and order"
```

---

## Task 3: Create handlers/new_chat.py (complete flow)

**Files:**
- Create: `src/codogram/handlers/new_chat.py`

**Step 1: Create the file**

```python
"""Unified /new_chat command for creating topics with Claude sessions.

Complete flow:
1. Show context (directory/branch) + choice (here/isolated)
2. If isolated + uncommitted: show uncommitted options
3. Show name prompt
4. Create thread or branch
"""
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from .. import strings
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from .common import (
    require_forum_group,
    require_claude_ready,
    set_flow_state,
    get_flow_state,
    clear_flow_state,
)
from ..domain.worktree_state import WorktreeState, get_worktree_state
from ..services.create_flow import create_flow_service
from ..services.branch import do_branch_create
from ..services.launch import create_thread_with_session
from ..git_utils import (
    is_git_repo,
    has_uncommitted_changes,
    get_default_branch,
    branch_exists,
)
from ..tmux import TmuxSession

router = Router(name="new_chat")


# ===== Keyboards =====

def _context_keyboard(has_git: bool) -> InlineKeyboardMarkup:
    """Build keyboard for context step."""
    if has_git:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=strings.BTN_CREATE_HERE, callback_data="nc_here"),
                InlineKeyboardButton(text=strings.BTN_CREATE_ISOLATED, callback_data="nc_isolated"),
            ],
            [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="nc_cancel")],
        ])
    else:
        # No git - only "create here" option, go straight to name
        return None


def _name_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for name prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_MAGIC_NAME, callback_data="nc_magic")],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="nc_cancel")],
    ])


def _uncommitted_keyboard(name: str) -> InlineKeyboardMarkup:
    """Build keyboard for uncommitted changes."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.NC_UNCOMMITTED_CLEAN,
            callback_data=f"nc_uncommitted_clean:{name}"
        )],
        [InlineKeyboardButton(
            text=strings.NC_UNCOMMITTED_COMMIT,
            callback_data=f"nc_uncommitted_commit:{name}"
        )],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="nc_cancel")],
    ])


# ===== Main command =====

@router.message(Command("new_chat", "nc", ignore_case=True))
async def cmd_new_chat(message: Message, telegram_queue: TelegramQueue):
    """Create a new chat (topic + Claude session)."""
    if not await require_forum_group(message, telegram_queue):
        return
    if not await require_claude_ready(message, telegram_queue):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_REGISTERED)
        return

    # Determine current context (directory and branch)
    current_thread = project.threads.get(thread_id)
    directory = project.cwd
    branch = get_default_branch(Path(project.cwd)) if is_git_repo(Path(project.cwd)) else "main"

    if current_thread and current_thread.worktree_path:
        state = get_worktree_state(current_thread, Path(project.cwd))
        if state == WorktreeState.OK:
            directory = current_thread.worktree_path
            branch = current_thread.name

    # Check if git repo exists (for isolated option)
    has_git = is_git_repo(Path(project.cwd))

    if not has_git:
        # No git - skip to name prompt directly
        prompt_ids = await telegram_queue.reply(
            message,
            strings.NEW_CHAT_NAME_PROMPT,
            reply_markup=_name_keyboard(),
        )
        set_flow_state(chat_id, thread_id, {
            "type": "nc_awaiting_name",
            "create_type": "thread",
            "prompt_message_id": prompt_ids[0] if prompt_ids else None,
        })
        return

    # Show context + choice
    if branch == get_default_branch(Path(project.cwd)):
        context_text = strings.NEW_CHAT_CONTEXT_MAIN.format(directory=directory, branch=branch)
    else:
        context_text = strings.NEW_CHAT_CONTEXT.format(directory=directory, branch=branch)

    set_flow_state(chat_id, thread_id, {
        "type": "nc_context",
        "directory": directory,
        "branch": branch,
    })

    await telegram_queue.reply(
        message,
        f"{context_text}\n\n{strings.NEW_CHAT_CHOOSE}",
        reply_markup=_context_keyboard(has_git),
    )


# ===== Step 1 callbacks: Create here vs Isolated =====

@router.callback_query(F.data == "nc_here")
async def on_nc_here(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create chat in current directory (thread)."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)

    # Show name prompt
    await telegram_queue.edit(
        callback.message,
        strings.NEW_CHAT_NAME_PROMPT,
        reply_markup=_name_keyboard(),
    )
    await callback.answer()

    set_flow_state(chat_id, thread_id, {
        "type": "nc_awaiting_name",
        "create_type": "thread",
        "prompt_message_id": callback.message.message_id,
    })


@router.callback_query(F.data == "nc_isolated")
async def on_nc_isolated(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create isolated branch."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)

    # Show name prompt for branch
    await telegram_queue.edit(
        callback.message,
        strings.NEW_CHAT_NAME_PROMPT,
        reply_markup=_name_keyboard(),
    )
    await callback.answer()

    set_flow_state(chat_id, thread_id, {
        "type": "nc_awaiting_name",
        "create_type": "branch",
        "prompt_message_id": callback.message.message_id,
    })


@router.callback_query(F.data == "nc_cancel")
async def on_nc_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Cancel new chat creation."""
    clear_flow_state(callback.message.chat.id, callback.message.message_thread_id)
    await callback.message.delete()
    await callback.answer()


# ===== Step 2/3: Name handling =====

@router.callback_query(F.data == "nc_magic")
async def on_nc_magic(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Generate magic name and create."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    state = get_flow_state(chat_id, thread_id)

    if not state or state.get("type") != "nc_awaiting_name":
        await callback.answer(strings.SESSION_EXPIRED)
        return

    create_type = state.get("create_type")
    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    name = create_flow_service.get_magic_name(project)

    # For branch: check uncommitted first
    if create_type == "branch":
        if has_uncommitted_changes(Path(project.cwd)):
            await telegram_queue.edit(
                callback.message,
                strings.NC_UNCOMMITTED,
                reply_markup=_uncommitted_keyboard(name),
            )
            await callback.answer()
            return

    # Create directly
    await telegram_queue.edit(callback.message, strings.NEW_CHAT_CREATING.format(name=name))
    await callback.answer()

    await _do_create(callback.bot, chat_id, thread_id, project, name, create_type, telegram_queue)


async def handle_name_input(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Handle text message as name input. Returns True if handled."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    state = get_flow_state(chat_id, thread_id)

    if not state or state.get("type") != "nc_awaiting_name":
        return False

    create_type = state.get("create_type")
    prompt_message_id = state.get("prompt_message_id")
    clear_flow_state(chat_id, thread_id)

    # Delete the prompt
    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id, prompt_message_id)
        except Exception:
            pass

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, strings.PROJECT_NOT_FOUND)
        return True

    name, error = create_flow_service.validate_name(message.text.strip(), project)
    if error:
        await telegram_queue.reply(message, error)
        return True

    # For branch: check preconditions
    if create_type == "branch":
        can_create, err, warning = create_flow_service.check_branch_preconditions(project, name)
        if err:
            await telegram_queue.reply(message, err)
            return True
        if warning:
            # Uncommitted changes
            await telegram_queue.reply(
                message,
                strings.NC_UNCOMMITTED,
                reply_markup=_uncommitted_keyboard(name),
            )
            return True

    # Create
    await telegram_queue.reply(message, strings.NEW_CHAT_CREATING.format(name=name))
    await _do_create(message.bot, chat_id, thread_id, project, name, create_type, telegram_queue)
    return True


# ===== Uncommitted changes callbacks =====

@router.callback_query(F.data.startswith("nc_uncommitted_clean:"))
async def on_nc_uncommitted_clean(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Create from last commit (ignore uncommitted)."""
    name = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    await telegram_queue.edit(callback.message, strings.NEW_CHAT_CREATING.format(name=name))
    await callback.answer()

    await _do_create(callback.bot, chat_id, thread_id, project, name, "branch", telegram_queue)


@router.callback_query(F.data.startswith("nc_uncommitted_commit:"))
async def on_nc_uncommitted_commit(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Ask Claude to commit first."""
    name = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    # Find current thread's tmux
    current_thread = project.threads.get(thread_id)
    if current_thread:
        tmux_name = current_thread.get_tmux_session(project.project_name)
        cwd = current_thread.worktree_path or project.cwd
        tmux = TmuxSession(tmux_name, cwd)
        if tmux.exists():
            tmux.send("Commit current changes in logical chunks with descriptive messages.")

    await telegram_queue.edit(
        callback.message,
        strings.BRANCH_COMMIT_SENT.format(branch_name=name),
    )
    await callback.answer()


# ===== Creation logic =====

async def _do_create(bot, chat_id: int, thread_id: int | None, project, name: str, create_type: str, telegram_queue: TelegramQueue):
    """Actually create the thread or branch."""
    if create_type == "branch":
        default_branch = get_default_branch(Path(project.cwd))
        result = await do_branch_create(bot, chat_id, project, name, default_branch)
    else:
        result = await create_thread_with_session(
            bot=bot,
            chat_id=chat_id,
            project=project,
            name=name,
        )

    if result:
        await telegram_queue.send(chat_id, strings.NEW_CHAT_CREATED.format(name=name), thread_id=thread_id)
    else:
        await telegram_queue.send(chat_id, strings.NEW_CHAT_ERROR, thread_id=thread_id)
```

**Step 2: Verify syntax**

```bash
python -m py_compile src/codogram/handlers/new_chat.py
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/new_chat.py
git commit -m "feat: add handlers/new_chat.py with complete unified flow"
```

---

## Task 4: Register new_chat router in main.py

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Find handler imports and router registration**

Look for pattern like:
```python
from .handlers import start, threads, branches, ...
dp.include_router(threads.router)
```

**Step 2: Add new_chat import and router**

Add `new_chat` to imports and `dp.include_router(new_chat.router)` BEFORE threads/branches.

**Step 3: Verify syntax**

```bash
python -m py_compile src/codogram/main.py
```

**Step 4: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat: register new_chat router"
```

---

## Task 5: Strip handlers/threads.py to pure alias

**Files:**
- Modify: `src/codogram/handlers/threads.py`

**Step 1: Replace entire file**

```python
"""Thread aliases - redirect to /new_chat."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ..telegram_queue import TelegramQueue
from .new_chat import cmd_new_chat

router = Router(name="threads")


@router.message(Command("thread", "thread_create", ignore_case=True))
async def cmd_thread(message: Message, telegram_queue: TelegramQueue):
    """Alias for /new_chat."""
    await cmd_new_chat(message, telegram_queue)


@router.message(Command("thread_delete", ignore_case=True))
async def cmd_thread_delete(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish_chat."""
    await telegram_queue.reply(message, "`[i]` Use /finish_chat to archive chats")
```

**Step 2: Verify syntax**

```bash
python -m py_compile src/codogram/handlers/threads.py
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/threads.py
git commit -m "refactor: threads.py now pure alias to new_chat"
```

---

## Task 6: Strip handlers/branches.py to pure alias

**Files:**
- Modify: `src/codogram/handlers/branches.py`

**Step 1: Replace entire file**

```python
"""Branch aliases - redirect to /new_chat."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from .. import strings
from ..telegram_queue import TelegramQueue
from .new_chat import cmd_new_chat

router = Router(name="branches")


@router.message(Command("branch", "branch_create", ignore_case=True))
async def cmd_branch(message: Message, telegram_queue: TelegramQueue):
    """Alias for /new_chat."""
    await cmd_new_chat(message, telegram_queue)


@router.message(Command("branch_finish", ignore_case=True))
async def cmd_branch_finish(message: Message, telegram_queue: TelegramQueue):
    """Deprecated: redirect to /finish_chat."""
    await telegram_queue.reply(message, strings.BRANCH_FINISH_USE_FINISH)
```

**Step 2: Verify syntax**

```bash
python -m py_compile src/codogram/handlers/branches.py
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/branches.py
git commit -m "refactor: branches.py now pure alias to new_chat"
```

---

## Task 7: Rename handlers/finish.py to finish_chat.py

**Files:**
- Rename: `src/codogram/handlers/finish.py` → `src/codogram/handlers/finish_chat.py`
- Modify: `src/codogram/handlers/__init__.py`
- Modify: `src/codogram/main.py`

**Step 1: Rename file**

```bash
git mv src/codogram/handlers/finish.py src/codogram/handlers/finish_chat.py
```

**Step 2: Update Command decorator in finish_chat.py**

Change:
```python
@router.message(Command("finish", ignore_case=True))
```
To:
```python
@router.message(Command("finish_chat", "finish", "archive", "fc", ignore_case=True))
```

Also update router name:
```python
router = Router(name="finish_chat")
```

**Step 3: Update imports in main.py**

Change `from .handlers import ... finish ...` to `finish_chat`.

**Step 4: Update __init__.py if it exports handlers**

**Step 5: Verify syntax**

```bash
python -m py_compile src/codogram/handlers/finish_chat.py
python -m py_compile src/codogram/main.py
```

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: rename finish.py to finish_chat.py, add aliases"
```

---

## Task 8: Update handlers/sessions.py

**Files:**
- Modify: `src/codogram/handlers/sessions.py`

**Step 1: Update /clear to /clear_context**

Change:
```python
@router.message(Command("clear", ignore_case=True))
async def cmd_clear(message: Message, telegram_queue: TelegramQueue):
```
To:
```python
@router.message(Command("clear_context", "clear", "new", ignore_case=True))
async def cmd_clear_context(message: Message, telegram_queue: TelegramQueue):
```

**Step 2: Remove separate /new handler if exists**

The `/new` is now an alias of `/clear_context`.

**Step 3: Add /reset_chat if restart exists**

Find `/restart` handler and add alias:
```python
@router.message(Command("reset_chat", "restart", ignore_case=True))
async def cmd_reset_chat(message: Message, telegram_queue: TelegramQueue):
```

**Step 4: Verify syntax**

```bash
python -m py_compile src/codogram/handlers/sessions.py
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/sessions.py
git commit -m "feat: add clear_context and reset_chat as primary commands"
```

---

## Task 9: Update handlers/create_flow.py for new_chat integration

**Files:**
- Modify: `src/codogram/handlers/create_flow.py`
- Modify: `src/codogram/handlers/messages.py` (if it calls handle_name_input)

**Step 1: Check messages.py for create_flow usage**

Find where `handle_name_input` is called.

**Step 2: Update to use new_chat.handle_name_input**

Change import from `create_flow` to `new_chat`:
```python
from .new_chat import handle_name_input
```

**Step 3: Simplify or remove create_flow.py**

Since new_chat.py now handles everything, create_flow.py may only be needed for its callbacks (`create_cancel`). If those callbacks are no longer used, the file can be removed.

Check if any code still uses `create_magic:*` callbacks. If not, delete the file.

**Step 4: Commit**

```bash
git add src/codogram/handlers/
git commit -m "refactor: integrate new_chat.handle_name_input, simplify create_flow"
```

---

## Task 10: Update handlers/settings.py /help

**Files:**
- Modify: `src/codogram/handlers/settings.py`

**Step 1: Update cmd_help**

```python
@router.message(Command("help", ignore_case=True))
async def cmd_help(message: Message, telegram_queue: TelegramQueue):
    """Show help with Close button."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Close", callback_data="help_close")]
    ])
    await telegram_queue.reply(message, strings.HELP_TEXT, reply_markup=keyboard)


@router.callback_query(F.data == "help_close")
async def on_help_close(callback: CallbackQuery):
    """Close help message."""
    await callback.message.delete()
    await callback.answer()
```

**Step 2: Add import for F if needed**

```python
from aiogram import Router, F
```

**Step 3: Verify syntax**

```bash
python -m py_compile src/codogram/handlers/settings.py
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/settings.py
git commit -m "feat: update /help with new text and Close button"
```

---

## Task 11: Add hard_reset alias

**Files:**
- Find and modify reset handler (likely in `start.py` or `sessions.py`)

**Step 1: Find reset_all handler**

```bash
grep -r "reset_all" src/codogram/handlers/
```

**Step 2: Add hard_reset alias**

Change:
```python
@router.message(Command("reset_all", ignore_case=True))
```
To:
```python
@router.message(Command("hard_reset", "reset_all", ignore_case=True))
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/
git commit -m "feat: add hard_reset alias to reset_all"
```

---

## Task 12: Update E2E tests

**Files:**
- Modify: `docs/e2e/commands/threads.md` → rename to `new_chat.md`
- Modify: `docs/e2e/commands/branches.md` → merge into `new_chat.md`
- Update: `docs/e2e/suites.md`

**Step 1: Create new_chat.md**

Document test cases for:
- `/new_chat` from General (main)
- `/new_chat` from worktree topic
- `/new_chat` with no git repo
- Magic name flow
- Uncommitted changes flow
- Alias commands (`/thread`, `/branch`, `/nc`)

**Step 2: Update finish tests for /finish_chat**

**Step 3: Commit**

```bash
git add docs/e2e/
git commit -m "docs: update E2E tests for command merge"
```

---

## Task 13: Manual E2E test

**Steps:**
1. Start bot: `./kill-instance-and-start-from-worktree.sh`
2. Test `/new_chat` shows context and options
3. Test "Create here" → name → creates thread
4. Test "Create isolated" → name → creates branch
5. Test uncommitted changes flow
6. Test `/thread` redirects to `/new_chat` behavior
7. Test `/branch` redirects to `/new_chat` behavior
8. Test `/help` shows new text with Close button
9. Test `/finish_chat` works
10. Test `/clear_context` works
11. Test `/reset_chat` works
12. Check menu shows new commands

---

## Task 14: Final cleanup and commit

**Step 1: Remove any unused imports/code**

```bash
grep -r "create_magic" src/codogram/
grep -r "bc_base\|bc_create\|bc_commit" src/codogram/
grep -r "thread_create_confirm" src/codogram/
```

Remove any remaining references.

**Step 2: Final commit**

```bash
git add -A
git commit -m "chore: cleanup unused code from command merge"
```
