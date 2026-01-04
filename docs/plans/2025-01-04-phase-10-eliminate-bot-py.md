# Phase 10: Eliminate bot.py Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Completely eliminate bot.py by moving all remaining code to handlers/ and services/

**Architecture:**
- `cb_cancel` + `require_forum_group` + `_flow_state` → handlers/common.py
- `_do_branch_create` + `_do_branch_cleanup` → services/branch.py
- `on_message` logic → services/message_router.py + handlers/messages.py
- Legacy FSM functions → deleted (handlers/start.py already uses aiogram FSM)

**Tech Stack:** Python, aiogram 3.x, pytest

---

## Background

### Current State (bot.py = 522 lines)

**Handlers (2):**
- `cb_cancel` (line 277) - generic cancel for branches/threads buttons
- `on_message` (line 345) - message routing + legacy FSM

**Helpers (4) - imported by handlers/):**
- `require_forum_group` (line 26)
- `_start_state` dict (line 22)
- `_do_branch_create` (line 325)
- `_do_branch_cleanup` (line 286)

**Legacy FSM functions (used by on_message):**
- `_start_project_flow`, `_connect_or_launch`, `_start_thread_flow`
- `launch_claude_in_thread`, `_make_task_starters`
- `get_session_for_chat`, `get_project_for_chat`, `is_claude_running`, `show_status`

### Target State

- bot.py deleted
- handlers/common.py: `cb_cancel`, `require_forum_group`, `_flow_state`
- services/branch.py: `do_branch_create`, `do_branch_cleanup`
- services/message_router.py: routing logic
- handlers/messages.py: thin handler for message routing

### Key Insight: Legacy FSM is Dead Code

handlers/start.py already handles all start flow states with aiogram FSM:
- `StartFlow.awaiting_project_name`
- `StartFlow.awaiting_custom_path`
- `StartFlow.awaiting_clone_url`

The legacy FSM in on_message (`_start_state` dict) is never triggered because aiogram FSM catches messages first. We can safely delete all legacy FSM code.

---

## Task 1: Create handlers/common.py

**Files:**
- Create: `src/codogram/handlers/common.py`

**Step 1: Create the file**

```python
"""Common handlers and helpers used by multiple modules."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

router = Router(name="common")

# State dict for thread_create flow (threads.py uses this)
# TODO: Migrate to aiogram FSM in future
_flow_state: dict[int, dict] = {}


async def require_forum_group(message: Message) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await message.answer("`[!]` This command requires a group with topics.", parse_mode="Markdown")
        return False
    if not message.chat.is_forum:
        await message.answer("`[!]` Topics required. Enable in group settings -> Topics", parse_mode="Markdown")
        return False
    return True


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    _flow_state.pop(chat_id, None)
    await callback.message.edit_text("Cancelled.")
    await callback.answer()
```

**Step 2: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.common import router, require_forum_group, _flow_state; print('OK')"
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/common.py
git commit -m "feat(handlers): add common.py with cb_cancel and require_forum_group"
```

---

## Task 2: Create services/branch.py

**Files:**
- Create: `src/codogram/services/branch.py`

**Step 1: Create the file**

Copy logic from bot.py `_do_branch_create` and `_do_branch_cleanup`:

```python
"""Branch/worktree operations."""
import subprocess
from pathlib import Path

from aiogram import Bot
from aiogram.types import Message

from ..session_manager import project_manager, ProjectState, ThreadInfo
from ..worktree import remove_worktree
from ..logging_config import logger


async def do_branch_cleanup(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    thread: ThreadInfo,
    force: bool,
) -> None:
    """Clean up worktree, tmux, and archive topic.

    Args:
        bot: Telegram bot instance
        chat_id: Chat ID for the topic
        project: Project state
        thread: Thread to cleanup
        force: If True, force delete branch even if unmerged
    """
    main_repo = Path(project.cwd)
    worktree_path = Path(thread.worktree_path) if thread.worktree_path else None
    branch_name = thread.name

    # Cancel background tasks
    if thread.watcher_task:
        thread.watcher_task.cancel()
    if thread.poller_task:
        thread.poller_task.cancel()
    if thread.binding_task:
        thread.binding_task.cancel()

    # Kill tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Remove worktree and branch
    if worktree_path:
        remove_worktree(main_repo, worktree_path, branch_name, delete_branch=True, force=force)

    # Archive topic
    try:
        await bot.close_forum_topic(chat_id, thread.thread_id)
        await bot.edit_forum_topic(chat_id, thread.thread_id, icon_custom_emoji_id="5357315181649076022")
    except Exception:
        pass  # Topic may already be closed

    # Update thread state
    thread.archived = True
    thread.worktree_path = None
    thread.session_id = None
    project_manager._save()


async def do_branch_create(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    branch_name: str,
    base_branch: str,
) -> ThreadInfo | None:
    """Create topic + worktree + launch Claude.

    Returns:
        ThreadInfo if successful, None otherwise
    """
    from .launch import create_thread_with_session

    thread = await create_thread_with_session(
        bot=bot,
        chat_id=chat_id,
        project=project,
        name=branch_name,
        create_worktree=True,
        base_branch=base_branch,
    )

    return thread
```

**Step 2: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.services.branch import do_branch_create, do_branch_cleanup; print('OK')"
```

**Step 3: Commit**

```bash
git add src/codogram/services/branch.py
git commit -m "feat(services): add branch.py with do_branch_create and do_branch_cleanup"
```

---

## Task 3: Update handlers/threads.py imports

**Files:**
- Modify: `src/codogram/handlers/threads.py`

**Step 1: Update imports**

Change:
```python
from ..bot import require_forum_group, _start_state
```

To:
```python
from .common import require_forum_group, _flow_state
```

**Step 2: Replace _start_state with _flow_state**

Find and replace all occurrences of `_start_state` with `_flow_state` in the file.

**Step 3: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.threads import router; print('OK')"
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/threads.py
git commit -m "refactor(handlers): threads.py imports from common instead of bot"
```

---

## Task 4: Update handlers/branches.py imports

**Files:**
- Modify: `src/codogram/handlers/branches.py`

**Step 1: Update imports**

Change:
```python
from ..bot import require_forum_group, _start_state, _do_branch_create, _do_branch_cleanup
```

To:
```python
from .common import require_forum_group, _flow_state
from ..services.branch import do_branch_create, do_branch_cleanup
```

**Step 2: Replace function names**

- `_start_state` → `_flow_state`
- `_do_branch_create` → `do_branch_create`
- `_do_branch_cleanup` → `do_branch_cleanup`

**Step 3: Update function calls**

The new functions have different signatures:

Old `_do_branch_create(message, project, branch_name, base_branch)`:
```python
await _do_branch_create(message, project, branch_name, base_branch)
```

New `do_branch_create(bot, chat_id, project, branch_name, base_branch)`:
```python
await do_branch_create(message.bot, message.chat.id, project, branch_name, base_branch)
```

Old `_do_branch_cleanup(message, project, thread, force)`:
```python
await _do_branch_cleanup(callback.message, project, thread, force=False)
```

New `do_branch_cleanup(bot, chat_id, project, thread, force)`:
```python
await do_branch_cleanup(callback.bot, callback.message.chat.id, project, thread, force=False)
```

**Step 4: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.branches import router; print('OK')"
```

**Step 5: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Step 6: Commit**

```bash
git add src/codogram/handlers/branches.py
git commit -m "refactor(handlers): branches.py imports from common and services/branch"
```

---

## Task 5: Create services/message_router.py

**Files:**
- Create: `src/codogram/services/message_router.py`

**Step 1: Create the file**

```python
"""Message routing to tmux sessions."""
from dataclasses import dataclass
from enum import Enum

from ..session_manager import project_manager, ProjectState, ThreadInfo
from ..tmux import TmuxSession
from ..logging_config import logger


class RouteAction(Enum):
    """Possible routing actions."""
    SEND_TO_TMUX = "send_to_tmux"
    CREATE_PENDING = "create_pending"
    SKIP_PENDING = "skip_pending"
    START_BINDING = "start_binding"
    NO_PROJECT = "no_project"
    NO_TMUX = "no_tmux"


@dataclass
class RouteResult:
    """Result of message routing decision."""
    action: RouteAction
    project: ProjectState | None = None
    thread: ThreadInfo | None = None
    tmux_name: str | None = None
    cwd: str | None = None


class MessageRouterService:
    """Route messages to appropriate tmux sessions."""

    def __init__(self, pm=None):
        self.pm = pm or project_manager

    def route(self, chat_id: int, thread_id: int | None, text: str) -> RouteResult:
        """Determine where to route a message.

        Args:
            chat_id: Telegram chat ID
            thread_id: Topic thread ID (None for main/private)
            text: Message text

        Returns:
            RouteResult with action and context
        """
        project = self.pm.get_by_chat(chat_id)
        if not project:
            return RouteResult(action=RouteAction.NO_PROJECT)

        # Get thread for this topic
        thread = project.threads.get(thread_id)

        # Unknown topic - need to create pending
        if thread_id is not None and not thread:
            return RouteResult(
                action=RouteAction.CREATE_PENDING,
                project=project,
            )

        # Auto-create main thread if missing
        if thread_id is None and not thread:
            thread = project.get_or_create_thread(None, "main")
            self.pm._save()

        # Skip pending threads
        if thread and thread.name == "pending":
            return RouteResult(action=RouteAction.SKIP_PENDING)

        # Check if session needs binding
        if thread and thread.session_id is None:
            return RouteResult(
                action=RouteAction.START_BINDING,
                project=project,
                thread=thread,
            )

        # Ready to send to tmux
        tmux_name = thread.get_tmux_session(project.project_name)
        return RouteResult(
            action=RouteAction.SEND_TO_TMUX,
            project=project,
            thread=thread,
            tmux_name=tmux_name,
            cwd=project.cwd,
        )

    def send_to_tmux(self, result: RouteResult, text: str) -> bool:
        """Send text to tmux session.

        Returns True if sent successfully.
        """
        if not result.tmux_name or not result.cwd:
            return False

        tmux = TmuxSession(result.tmux_name, result.cwd)
        if not tmux.exists():
            logger.warning(f"no_tmux_session: {result.tmux_name}")
            return False

        tmux.send(text)
        logger.debug(f"sent_to_tmux: {text[:50]}")
        return True
```

**Step 2: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.services.message_router import MessageRouterService, RouteAction; print('OK')"
```

**Step 3: Commit**

```bash
git add src/codogram/services/message_router.py
git commit -m "feat(services): add message_router.py for message routing logic"
```

---

## Task 6: Create handlers/messages.py

**Files:**
- Create: `src/codogram/handlers/messages.py`

**Step 1: Create the file**

```python
"""Message routing handler - routes messages to tmux sessions."""
import asyncio

from aiogram import Router
from aiogram.types import Message

from ..services.message_router import MessageRouterService, RouteAction
from ..session_manager import project_manager, ThreadInfo
from ..logging_config import logger

router = Router(name="messages")

# Service instance
_message_router = MessageRouterService()


@router.message()
async def on_message(message: Message):
    """Route regular messages to tmux sessions.

    This is the catch-all handler - registered last so commands
    and FSM states are handled first by other routers.
    """
    text = message.text
    if not text:
        return

    # Log
    text_preview = text[:100] if len(text) > 100 else text
    logger.info(
        f"Incoming message from user={message.from_user.id} "
        f"chat={message.chat.id} thread={message.message_thread_id}: {text_preview}"
    )

    # Skip commands
    if text.startswith("/"):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    # Route the message
    result = _message_router.route(chat_id, thread_id, text)

    match result.action:
        case RouteAction.NO_PROJECT:
            # Silent - no project registered
            return

        case RouteAction.CREATE_PENDING:
            # Unknown topic - create pending thread
            thread = ThreadInfo(thread_id=thread_id, name="pending")
            result.project.threads[thread_id] = thread
            project_manager._save()
            await message.answer("Use /start or /thread_create to connect Claude to this topic")
            return

        case RouteAction.SKIP_PENDING:
            # Pending thread - skip silently
            return

        case RouteAction.START_BINDING:
            # Need to bind session - start binding task
            await _start_binding(message, result)
            # Still try to send to tmux
            _try_send_to_tmux(result, text)
            return

        case RouteAction.SEND_TO_TMUX:
            success = _message_router.send_to_tmux(result, text)
            if not success and message.chat.id < 0:
                await message.answer("No active Claude session. Use /start to launch.")

        case RouteAction.NO_TMUX:
            if message.chat.id < 0:
                await message.answer("No active Claude session. Use /start to launch.")


def _try_send_to_tmux(result, text: str) -> bool:
    """Try to send message to tmux if session exists."""
    if result.tmux_name and result.cwd:
        from ..tmux import TmuxSession
        tmux = TmuxSession(result.tmux_name, result.cwd)
        if tmux.exists():
            tmux.send(text)
            return True
    return False


async def _start_binding(message: Message, result):
    """Start session binding for unbound thread."""
    from ..history_watcher import poll_for_session_thread
    from .. import main

    thread = result.thread
    project = result.project

    thread.last_sent_message = message.text

    if not thread.binding_task or thread.binding_task.done():
        logger.debug(f"Starting binding task for thread {thread.name}")

        async def start_poller(p):
            from ..permission_poller import create_poller_task
            return await create_poller_task(message.bot, p, main.telegram_queue)

        async def start_watcher(p, send_missed=False):
            from ..watcher import create_watcher_task
            return await create_watcher_task(message.bot, p, main.telegram_queue, send_missed)

        thread.binding_task = asyncio.create_task(
            poll_for_session_thread(
                project, thread, message.bot,
                start_poller, start_watcher, main.telegram_queue
            )
        )
```

**Step 2: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers.messages import router; print('OK')"
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/messages.py
git commit -m "feat(handlers): add messages.py for message routing to tmux"
```

---

## Task 7: Update handlers/__init__.py

**Files:**
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Update the file**

```python
"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, threads, branches, sessions, settings, common, messages


def register_handlers(dp: Dispatcher):
    """Register all handler routers.

    Note: AdminMiddleware is registered on dp level in main.py,
    protecting ALL routers. No need to add it here.

    Order matters:
    - Specific command handlers first
    - common.router has cb_cancel (generic cancel)
    - messages.router is catch-all (must be last)
    """
    dp.include_router(permissions.router)   # Permission callbacks
    dp.include_router(start.router)         # /start, /restart + FSM
    dp.include_router(threads.router)       # /thread_create, /thread_delete
    dp.include_router(branches.router)      # /branch_create, /branch_finish
    dp.include_router(sessions.router)      # /new, /clear, /esc, /resume
    dp.include_router(settings.router)      # /settings, /auto_accept, /help
    dp.include_router(common.router)        # cb_cancel
    dp.include_router(messages.router)      # Catch-all for tmux routing (LAST!)
```

**Step 2: Verify import**

```bash
PYTHONPATH=src python -c "from codogram.handlers import register_handlers; print('OK')"
```

**Step 3: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/__init__.py
git commit -m "refactor(handlers): add common and messages to register_handlers"
```

---

## Task 8: Update main.py

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Remove bot.py import**

Remove:
```python
from .bot import router
```

And remove:
```python
dp.include_router(router)
```

**Step 2: Verify main.py works**

```bash
PYTHONPATH=src python -c "from codogram.main import main; print('OK')"
```

**Step 3: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add src/codogram/main.py
git commit -m "refactor(main): remove bot.py router import"
```

---

## Task 9: Delete bot.py

**Files:**
- Delete: `src/codogram/bot.py`

**Step 1: Verify no imports remain**

```bash
grep -rn "from .*bot import\|from \.bot import" src/codogram/
```

Expected: No output (no imports from bot.py)

**Step 2: Delete the file**

```bash
rm src/codogram/bot.py
```

**Step 3: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -10
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: delete bot.py - all code migrated to handlers/ and services/"
```

---

## Task 10: Final verification

**Step 1: Verify all imports work**

```bash
PYTHONPATH=src python -c "
from codogram.handlers import register_handlers
from codogram.handlers.common import require_forum_group, _flow_state, cb_cancel
from codogram.handlers.messages import on_message
from codogram.services.branch import do_branch_create, do_branch_cleanup
from codogram.services.message_router import MessageRouterService
print('All imports OK')
"
```

**Step 2: Run full test suite**

```bash
PYTHONPATH=src pytest tests/ -v
```

**Step 3: Count handlers/ lines**

```bash
wc -l src/codogram/handlers/*.py
```

**Step 4: Verify bot.py is gone**

```bash
ls src/codogram/bot.py 2>&1
```

Expected: `ls: cannot access 'src/codogram/bot.py': No such file or directory`

**Step 5: List all routers**

```bash
grep -h "router = Router" src/codogram/handlers/*.py
```

Expected: 8 routers (permissions, start, threads, branches, sessions, settings, common, messages)

**Step 6: Verify router registration order**

```bash
grep -A1 "dp.include_router" src/codogram/handlers/__init__.py
```

Expected order (messages MUST be last):
1. permissions.router
2. start.router (handles FSM states)
3. threads.router
4. branches.router
5. sessions.router
6. settings.router
7. common.router
8. messages.router (catch-all - LAST!)

This order is critical because:
- aiogram processes routers in registration order
- FSM state handlers in start.router MUST intercept before messages.router
- messages.router is catch-all and would swallow FSM messages if registered first

---

## Summary

**Files created:**
- `src/codogram/handlers/common.py` (~30 LOC)
- `src/codogram/handlers/messages.py` (~100 LOC)
- `src/codogram/services/branch.py` (~70 LOC)
- `src/codogram/services/message_router.py` (~90 LOC)

**Files modified:**
- `src/codogram/handlers/threads.py` (import change)
- `src/codogram/handlers/branches.py` (import change + function calls)
- `src/codogram/handlers/__init__.py` (add common, messages)
- `src/codogram/main.py` (remove bot.py import)

**Files deleted:**
- `src/codogram/bot.py` (522 lines → 0)

**What was deleted (not migrated):**
- Legacy FSM functions (`_start_project_flow`, `_connect_or_launch`, etc.)
  - Reason: handlers/start.py already handles all FSM states with aiogram FSM
- Helper functions (`get_session_for_chat`, `is_claude_running`, `show_status`, etc.)
  - Reason: Not used by any handler after migration
