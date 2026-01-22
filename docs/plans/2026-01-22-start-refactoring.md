# Start Flow Refactoring Implementation Plan (v2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split god-files `handlers/start.py` (1048 LOC) and `services/start_flow.py` (663 LOC) into smaller modules, fix hidden bugs, simplify architecture.

**Architecture:**
- Handlers only route events to services
- Services contain business logic
- Restart/Reset — simple services without FlowAction enum
- Handler registry instead of god-switch
- Each file < 300 LOC

**Tech Stack:** Python, aiogram 3.x, FSM states

---

## Key Changes from v1

| Aspect | v1 (mechanical split) | v2 (with simplifications) |
|--------|----------------------|---------------------------|
| Restart | FlowAction enum + switch | Simple service, 2 methods |
| Reset | FlowAction enum + switch | Simple service, 2 methods |
| Start handler | Big match statement | Handler registry (dict) |
| Silent failures | Copied as-is | Fixed with user feedback |
| Callback parsing | No validation | Try/except with error message |
| Blocking subprocess | Copied as-is | Fixed with asyncio.to_thread |

---

## Bugs to Fix During Refactoring

### 🔴 Critical (fix immediately)

| Bug | Location | Fix |
|-----|----------|-----|
| Silent return on launch in progress | `_launch_claude*` | Reply "Launch already in progress" |
| Silent return on missing project/thread | `_launch_claude_in_thread` | Reply error message |
| Callback data parsing crash | `on_resume_callback` | Try/except + callback.answer(error) |
| Blocking subprocess.run | `_launch_claude_in_thread:343` | `asyncio.to_thread()` |
| **worktree_recovery missing resume** | `worktree_recovery.py:130` | Pass `session_id` to launch_with_animation |
| **worktree_recovery no topic reopen** | `worktree_recovery.py` | Call `reopen_forum_topic` before launch |
| **worktree_recovery no icon restore** | `worktree_recovery.py` | Call `edit_forum_topic` to restore icon |
| **"Resume in main" no launch** | `worktree_recovery.py:93-112` | After archiving, launch Claude in main thread |

### 🟡 Medium (fix during refactor)

| Bug | Location | Fix |
|-----|----------|-----|
| No state on SELECT_TMUX | `_handle_result` | Add state for tmux selection |
| Cross-flow FSM conflict | `/restart` during StartFlow | Check and clear other flow states |

### 🟠 Low (improve during refactor)

| Bug | Location | Fix |
|-----|----------|-----|
| Exception swallowing | `reopen_forum_topic`, `edit_forum_topic` | Log exceptions instead of bare `pass` |
| Magic emoji ID hardcoded | `start.py:364` | Move to `strings.py` as `ICON_BALLOT_BOX`, `ICON_FOLDER` |

---

## Target Structure

**Note:** `handlers/worktree_recovery.py` will be **merged** into `handlers/start/launch.py` to eliminate code duplication and fix the missing session_id/reopen/icon bugs.

```
handlers/
├── start/
│   ├── __init__.py          # router
│   ├── commands.py          # /start (~80 LOC)
│   ├── fsm.py               # FSM state handlers (~70 LOC)
│   ├── callbacks.py         # start:*, select_tmux:* (~130 LOC)
│   ├── registry.py          # Handler registry for FlowAction (~150 LOC)
│   ├── launch.py            # Launch helpers (~180 LOC)
│   └── helpers.py           # Shared helpers (~50 LOC)
│
├── restart/
│   ├── __init__.py          # router
│   ├── handlers.py          # All restart handlers (~100 LOC)
│   └── service.py           # RestartService - simple, no enum (~50 LOC)
│
├── reset/
│   ├── __init__.py          # router
│   ├── handlers.py          # All reset handlers (~130 LOC)
│   └── service.py           # ResetService - simple, no enum (~60 LOC)

services/
├── start/
│   ├── __init__.py          # re-exports
│   ├── models.py            # FlowAction, FlowResult (~60 LOC)
│   ├── flow.py              # StartFlowService (~250 LOC)
│   └── utils.py             # Utilities (~80 LOC)
```

---

## Phase 1: Services Layer

### Task 1: Create services/start/models.py

**Files:**
- Create: `src/codogram/services/start/__init__.py`
- Create: `src/codogram/services/start/models.py`

**Step 1: Create package with models**

```python
# src/codogram/services/start/__init__.py
"""Start flow services."""
from .models import FlowAction, FlowResult

__all__ = ["FlowAction", "FlowResult"]
```

```python
# src/codogram/services/start/models.py
"""Models for start flow."""
from dataclasses import dataclass
from enum import Enum


class FlowAction(Enum):
    """Outcomes of start flow steps.

    Note: Restart/Reset have their own simple services without enums.
    """
    # Questions
    ASK_PROJECT_NAME = "ask_project_name"
    ASK_DIR_CHOICE = "ask_dir_choice"
    ASK_GIT_CHOICE = "ask_git_choice"
    ASK_GH_VISIBILITY = "ask_gh_visibility"
    ASK_CLONE_URL = "ask_clone_url"
    ASK_CLONE_URL_RETRY = "ask_clone_url_retry"
    ASK_CUSTOM_PATH = "ask_custom_path"
    ASK_LAUNCH_CONFIRM = "ask_launch_confirm"
    ASK_TMUX_SELECT = "ask_tmux_select"  # Renamed from SELECT_TMUX

    # Actions
    SHOW_STATUS = "show_status"
    LAUNCH = "launch"
    CONNECT = "connect"

    # Errors
    ERROR = "error"

    # Thread-specific
    THREAD_SHOW_STATUS = "thread_show_status"
    THREAD_LAUNCH = "thread_launch"
    UPGRADE_PENDING_THREAD = "upgrade_pending_thread"
    REGISTER_UNKNOWN_TOPIC = "register_unknown_topic"


@dataclass
class FlowResult:
    """Result of a start flow step."""
    action: FlowAction
    project: str | None = None
    path: str | None = None
    tmux_session: str | None = None
    tmux_list: list[str] | None = None
    error: str | None = None
    thread_id: int | None = None
    thread_name: str | None = None
```

**Step 2: Run tests**

```bash
pytest tests/test_start_flow_service.py -v -k "FlowAction or FlowResult"
```

**Step 3: Commit**

```bash
git add src/codogram/services/start/
git commit -m "refactor(start): create services/start/models.py"
```

---

### Task 2: Create services/start/utils.py

**Files:**
- Create: `src/codogram/services/start/utils.py`
- Modify: `src/codogram/services/start/__init__.py`

**Step 1: Create utils.py**

```python
# src/codogram/services/start/utils.py
"""Utility functions for start flow."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.session_manager import ProjectState


def build_announcement(project_name: str, tmux_name: str, is_forum: bool) -> str:
    """Build project ready announcement."""
    commands = [
        "• /esc — cancel operation",
        "• /clear_context — clear context",
        "• /auto_accept — toggle auto-accept",
    ]
    if is_forum:
        commands.extend([
            "• /new_chat — new topic or branch",
            "• /finish_chat — merge and archive",
        ])

    return f"""`[v]` Project `{project_name}` ready

Commands available in this chat:
{chr(10).join(commands)}

To see Claude UI: `tmux attach -t {tmux_name}`"""


def build_thread_announcement(thread_name: str, tmux_name: str) -> str:
    """Build short announcement for topics."""
    return f"""`[v]` Thread `{thread_name}` running

To see Claude UI: `tmux attach -t {tmux_name}`"""


def is_setup_phase(project: "ProjectState") -> bool:
    """Check if project is in setup phase (Claude never ran)."""
    main_thread = project.threads.get(None)
    if main_thread and main_thread.session_id:
        return False
    if project.session_id:  # Legacy
        return False
    return True
```

**Step 2: Update __init__.py**

```python
# src/codogram/services/start/__init__.py
"""Start flow services."""
from .models import FlowAction, FlowResult
from .utils import build_announcement, build_thread_announcement, is_setup_phase

__all__ = [
    "FlowAction", "FlowResult",
    "build_announcement", "build_thread_announcement", "is_setup_phase",
]
```

**Step 3: Commit**

```bash
git add src/codogram/services/start/
git commit -m "refactor(start): create services/start/utils.py"
```

---

### Task 3: Create services/start/flow.py

**Files:**
- Create: `src/codogram/services/start/flow.py`
- Modify: `src/codogram/services/start/__init__.py`

**Step 1: Move StartFlowService to flow.py**

Copy class from `services/start_flow.py`, but:
- Remove restart-related methods (`handle_restart`, `handle_restart_confirm`, `handle_cancel`)
- Remove `CANCELLED`, `ASK_RESTART_CONFIRM`, `RESTART_DONE` handling
- Update imports to use local `.models`

```python
# src/codogram/services/start/flow.py
"""StartFlowService - business logic for /start flow."""
from pathlib import Path
from typing import TYPE_CHECKING

from ...domain.validators import (
    is_valid_project_name, sanitize_project_name,
    validate_git_url, MAX_PROJECT_NAME_LENGTH,
)
from ...magic_names import get_random_magic_name
from ...tmux.launcher import resolve_project_path, git_init, git_init_with_github, git_clone
from ...tmux.session import find_all_tmux_by_cwd, find_tmux_by_convention, TmuxSession
from ...tmux.launcher import is_tmux_session_exists
from ...core.session_manager import ThreadInfo
from .models import FlowAction, FlowResult

if TYPE_CHECKING:
    from ...core.session_manager import ProjectManager


class StartFlowService:
    """Business logic for /start flow."""

    def __init__(self, project_manager: "ProjectManager"):
        self.pm = project_manager

    def handle_start(
        self, chat_id: int, args: list[str],
        chat_title: str | None = None, thread_id: int | None = None,
    ) -> FlowResult:
        """Entry point for /start command."""
        if thread_id is not None:
            return self._handle_topic_start(chat_id, thread_id, args, chat_title)

        if args:
            return self._validate_and_start(chat_id, args[0])

        project = self.pm.get_by_chat(chat_id)
        if project:
            thread = project.threads.get(thread_id)
            if thread and thread.name != "pending":
                return self._check_thread_tmux(project, thread)
            if self._is_claude_running(project):
                return FlowResult(
                    action=FlowAction.SHOW_STATUS,
                    project=project.project_name,
                    path=project.cwd,
                    tmux_session=project.tmux_session,
                )
            return self._start_project_flow(chat_id, project.project_name)

        if chat_title:
            sanitized = sanitize_project_name(chat_title)
            if sanitized:
                return self._start_project_flow(chat_id, sanitized)

        return FlowResult(action=FlowAction.ASK_PROJECT_NAME)

    # ... rest of methods (copy from original, removing restart-related) ...
```

**Step 2: Update __init__.py**

```python
from .flow import StartFlowService
# Add to __all__
```

**Step 3: Run tests**

```bash
pytest tests/test_start_flow_service.py -v
```

**Step 4: Commit**

```bash
git add src/codogram/services/start/
git commit -m "refactor(start): move StartFlowService to services/start/flow.py"
```

---

### Task 4: Create restart/service.py (simple, no enum)

**Files:**
- Create: `src/codogram/services/restart/__init__.py`
- Create: `src/codogram/services/restart/service.py`

**Step 1: Create simple RestartService**

```python
# src/codogram/services/restart/service.py
"""Simple restart service - no FlowAction enum needed."""
from typing import TYPE_CHECKING

from ..tmux.launcher import is_tmux_session_exists
from ..tmux.session import kill_tmux_session

if TYPE_CHECKING:
    from ..core.session_manager import ProjectManager


class RestartService:
    """Service for /restart command."""

    def __init__(self, project_manager: "ProjectManager"):
        self.pm = project_manager

    def get_session_to_restart(
        self, chat_id: int, thread_id: int | None = None
    ) -> str | None:
        """Get tmux session name to restart, or None if nothing to restart."""
        project = self.pm.get_by_chat(chat_id)
        if not project:
            return None

        if thread_id:
            thread = project.threads.get(thread_id)
            if not thread:
                return None
            tmux_name = thread.get_tmux_session(project.project_name)
        else:
            main_thread = project.threads.get(None)
            if main_thread:
                tmux_name = main_thread.get_tmux_session(project.project_name)
            elif project.tmux_session:
                tmux_name = project.tmux_session
            else:
                return None

        if not is_tmux_session_exists(tmux_name):
            return None

        return tmux_name

    def kill_session(self, tmux_name: str) -> bool:
        """Kill tmux session. Returns True if killed."""
        return kill_tmux_session(tmux_name)
```

```python
# src/codogram/services/restart/__init__.py
"""Restart service."""
from .service import RestartService

__all__ = ["RestartService"]
```

**Step 2: Commit**

```bash
git add src/codogram/services/restart/
git commit -m "refactor(restart): create simple RestartService without enum"
```

---

### Task 5: Create reset/service.py (simple, no enum)

**Files:**
- Create: `src/codogram/services/reset/__init__.py`
- Create: `src/codogram/services/reset/service.py`

**Step 1: Create simple ResetService**

```python
# src/codogram/services/reset/service.py
"""Simple reset service - no FlowAction enum needed."""
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ... import strings
from ...tmux.launcher import is_tmux_session_exists
from ...tmux.session import kill_tmux_session

if TYPE_CHECKING:
    from ...core.session_manager import ProjectManager, ProjectState


@dataclass
class CleanupResult:
    """Result of cleanup operation."""
    success: bool
    error: str | None = None


class ResetService:
    """Service for /hard_reset command."""

    def __init__(self, project_manager: "ProjectManager"):
        self.pm = project_manager

    def is_setup_phase(self, project: "ProjectState") -> bool:
        """Check if project is in setup phase."""
        main_thread = project.threads.get(None)
        if main_thread and main_thread.session_id:
            return False
        if project.session_id:
            return False
        return True

    def cleanup(self, project: "ProjectState", delete_directory: bool) -> CleanupResult:
        """Full project cleanup."""
        # 1. Kill all tmux sessions
        for thread in project.threads.values():
            tmux_name = thread.get_tmux_session(project.project_name)
            if is_tmux_session_exists(tmux_name):
                kill_tmux_session(tmux_name)

        # 2. Remove worktrees
        if project.cwd:
            for thread in project.threads.values():
                if thread.worktree_path:
                    try:
                        subprocess.run(
                            ["git", "worktree", "remove", "--force", thread.worktree_path],
                            cwd=project.cwd, capture_output=True,
                        )
                    except Exception:
                        pass

        # 3. Delete directory
        cleanup_failed = False
        if delete_directory and project.cwd:
            shutil.rmtree(project.cwd, ignore_errors=True)
            if Path(project.cwd).exists():
                cleanup_failed = True

        # 4. Remove from config
        if project.project_name in self.pm.projects:
            del self.pm.projects[project.project_name]
            self.pm._save()

        if cleanup_failed:
            return CleanupResult(
                success=False,
                error=strings.RESET_CLEANUP_FAILED.format(path=project.cwd)
            )
        return CleanupResult(success=True)
```

**Step 2: Commit**

```bash
git add src/codogram/services/reset/
git commit -m "refactor(reset): create simple ResetService without enum"
```

---

### Task 6: Update old start_flow.py for backward compat

**Files:**
- Modify: `src/codogram/services/start_flow.py`

**Step 1: Replace with re-exports**

```python
# src/codogram/services/start_flow.py
"""Backward compatibility - import from services.start instead."""
from .start import (
    FlowAction, FlowResult, StartFlowService,
    build_announcement, build_thread_announcement, is_setup_phase,
)
from .reset.service import CleanupResult
from .reset.service import ResetService

# Re-export cleanup_project as function for backward compat
def cleanup_project(project, delete_directory: bool) -> CleanupResult:
    from ..core.session_manager import project_manager
    service = ResetService(project_manager)
    return service.cleanup(project, delete_directory)

__all__ = [
    "FlowAction", "FlowResult", "StartFlowService", "CleanupResult",
    "build_announcement", "build_thread_announcement",
    "is_setup_phase", "cleanup_project",
]
```

**Step 2: Run all tests**

```bash
pytest tests/test_start_flow_service.py tests/test_handlers_start.py -v
```

**Step 3: Commit**

```bash
git add src/codogram/services/start_flow.py
git commit -m "refactor(start): backward compat re-exports from services/start"
```

---

## Phase 2: Handler Helpers

### Task 7: Create handlers/start/helpers.py

**Files:**
- Create: `src/codogram/handlers/start/__init__.py`
- Create: `src/codogram/handlers/start/helpers.py`

**Step 1: Create helpers with bug fixes**

```python
# src/codogram/handlers/start/helpers.py
"""Helper functions for start flow handlers."""
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ... import strings
from ...services.menu import register_menu_for_chat
from ...telegram.queue import TelegramQueue


async def register_chat_menu(bot: Bot, chat) -> None:
    """Register scope-based menu for chat."""
    await register_menu_for_chat(bot, chat.id, is_forum=chat.is_forum or False)


async def get_state_data(
    state: FSMContext,
    callback: CallbackQuery,
    queue: TelegramQueue,
    *keys: str,
) -> dict | None:
    """Get required FSM data, show error if missing."""
    data = await state.get_data()
    missing = [k for k in keys if k not in data]
    if missing:
        await state.clear()
        await queue.edit(callback.message, strings.START_SESSION_EXPIRED, parse_mode=None)
        await callback.answer()
        return None
    return data


async def get_state_data_msg(
    state: FSMContext,
    message: Message,
    queue: TelegramQueue,
    *keys: str,
) -> dict | None:
    """Get required FSM data for message handlers."""
    data = await state.get_data()
    missing = [k for k in keys if k not in data]
    if missing:
        await state.clear()
        await queue.reply(message, strings.START_SESSION_EXPIRED)
        return None
    return data


def parse_callback_data(data: str, expected_parts: int) -> tuple | None:
    """Safely parse callback data.

    Returns tuple of parts or None if invalid.
    🔴 FIX: Previously crashed on malformed callback data.
    """
    parts = data.split(":")
    if len(parts) < expected_parts:
        return None
    return tuple(parts)


def parse_thread_id(value: str) -> int | None:
    """Parse thread_id from callback data.

    🔴 FIX: Previously crashed on non-numeric values.
    """
    if value == "None":
        return None
    try:
        return int(value)
    except ValueError:
        return None  # Invalid, will be handled by caller
```

**Step 2: Create __init__.py**

```python
# src/codogram/handlers/start/__init__.py
"""Start flow handlers."""
from aiogram import Router

router = Router(name="start")
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/start/
git commit -m "refactor(start): create helpers.py with callback parsing fixes"
```

---

### Task 8: Create handlers/start/registry.py

**Files:**
- Create: `src/codogram/handlers/start/registry.py`

**Step 1: Create handler registry**

```python
# src/codogram/handlers/start/registry.py
"""Handler registry for FlowAction results.

Replaces god-switch in _handle_result with modular handlers.
"""
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ... import strings
from ...domain.states import StartFlow
from ...services.start import FlowAction, FlowResult
from ...telegram.queue import TelegramQueue
from ...start_flow import dir_not_found_keyboard, git_setup_keyboard, launch_confirm_keyboard
from ...telegram.keyboards.tmux_selector import create_tmux_selection_keyboard
from .helpers import register_chat_menu


# === Individual handlers ===

async def handle_ask_project_name(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.set_state(StartFlow.awaiting_project_name)
    if result.thread_id:
        await state.update_data(thread_id=result.thread_id)
    await queue.reply(msg, strings.START_PROJECT_NAME_PROMPT, parse_mode=None)


async def handle_ask_dir_choice(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.set_state(StartFlow.awaiting_dir_choice)
    await state.update_data(project=result.project, path=result.path)
    await queue.reply(msg, strings.START_DIR_CHOICE_PROMPT.format(path=result.path),
                      reply_markup=dir_not_found_keyboard())


async def handle_ask_git_choice(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.set_state(StartFlow.awaiting_git_choice)
    await state.update_data(project=result.project, path=result.path)
    await queue.reply(msg, strings.START_GIT_SETUP_PROMPT,
                      reply_markup=git_setup_keyboard(), parse_mode=None)


async def handle_ask_launch_confirm(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.set_state(StartFlow.awaiting_launch_confirm)
    await state.update_data(project=result.project, path=result.path)
    await queue.reply(msg, strings.START_LAUNCH_CONFIRM.format(path=result.path),
                      reply_markup=launch_confirm_keyboard())


async def handle_ask_tmux_select(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    # 🟡 FIX: Set state for tmux selection (was missing)
    await state.set_state(StartFlow.awaiting_tmux_select)
    await state.update_data(project=result.project)
    await queue.reply(msg, strings.START_TMUX_SELECT,
                      reply_markup=create_tmux_selection_keyboard(result.tmux_list, result.project),
                      parse_mode=None)


async def handle_show_status(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.clear()
    await register_chat_menu(msg.bot, msg.chat)
    await queue.reply(msg, strings.START_CLAUDE_RUNNING.format(
        project=result.project, tmux_session=result.tmux_session))


async def handle_error(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.clear()
    await queue.reply(msg, strings.START_ERROR.format(error=result.error), parse_mode=None)


async def handle_ask_clone_retry(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    # 🟡 FIX: Ensure we're in the right state
    await state.set_state(StartFlow.awaiting_clone_url)
    await queue.reply(msg, f"{result.error}\n\n{strings.GIT_URL_RETRY_PROMPT}")


async def handle_thread_show_status(msg: Message, state: FSMContext, result: FlowResult, queue: TelegramQueue):
    await state.clear()
    await register_chat_menu(msg.bot, msg.chat)
    await queue.reply(msg, strings.START_THREAD_RUNNING.format(
        thread_name=result.thread_name, tmux_session=result.tmux_session))


# === Registry ===

MESSAGE_HANDLERS: dict[FlowAction, callable] = {
    FlowAction.ASK_PROJECT_NAME: handle_ask_project_name,
    FlowAction.ASK_DIR_CHOICE: handle_ask_dir_choice,
    FlowAction.ASK_GIT_CHOICE: handle_ask_git_choice,
    FlowAction.ASK_LAUNCH_CONFIRM: handle_ask_launch_confirm,
    FlowAction.ASK_TMUX_SELECT: handle_ask_tmux_select,
    FlowAction.SHOW_STATUS: handle_show_status,
    FlowAction.ERROR: handle_error,
    FlowAction.ASK_CLONE_URL_RETRY: handle_ask_clone_retry,
    FlowAction.THREAD_SHOW_STATUS: handle_thread_show_status,
    # CONNECT, LAUNCH, THREAD_LAUNCH handled separately (need launch callback)
}


async def dispatch_result(
    msg: Message,
    state: FSMContext,
    result: FlowResult,
    queue: TelegramQueue,
    launch_callback=None,
):
    """Dispatch FlowResult to appropriate handler."""
    handler = MESSAGE_HANDLERS.get(result.action)
    if handler:
        await handler(msg, state, result, queue)
        return

    # Special cases needing launch callback
    if result.action == FlowAction.CONNECT:
        await state.clear()
        await _connect_to_session(msg, result, queue)
    elif result.action == FlowAction.LAUNCH:
        await state.clear()
        if launch_callback:
            await launch_callback(msg, result, queue)
    elif result.action in (FlowAction.THREAD_LAUNCH, FlowAction.UPGRADE_PENDING_THREAD, FlowAction.REGISTER_UNKNOWN_TOPIC):
        await state.clear()
        if result.action == FlowAction.UPGRADE_PENDING_THREAD:
            await queue.reply(msg, strings.START_THREAD_UPGRADED.format(thread_name=result.thread_name))
        elif result.action == FlowAction.REGISTER_UNKNOWN_TOPIC:
            await queue.reply(msg, strings.START_TOPIC_REGISTERED.format(thread_name=result.thread_name))
        if launch_callback:
            await launch_callback(msg, result, queue, thread=True)


async def _connect_to_session(msg: Message, result: FlowResult, queue: TelegramQueue):
    """Connect to existing tmux session."""
    from ...core.session_manager import project_manager

    project = project_manager.get_by_chat(msg.chat.id)
    if not project:
        # 🔴 FIX: Was silent failure
        await queue.reply(msg, strings.PROJECT_NOT_FOUND, parse_mode=None)
        return

    project.tmux_session = result.tmux_session
    project_manager._save()
    await register_chat_menu(msg.bot, msg.chat)
    await queue.reply(msg, strings.START_CONNECTED.format(tmux_session=result.tmux_session))
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/start/registry.py
git commit -m "refactor(start): create handler registry, fix silent failures"
```

---

### Task 9: Create handlers/start/launch.py + merge worktree_recovery.py

**Files:**
- Create: `src/codogram/handlers/start/launch.py`
- Merge: `src/codogram/handlers/worktree_recovery.py` → into launch.py
- Delete: `src/codogram/handlers/worktree_recovery.py` (after integration)

**Step 1: Create launch.py with all fixes + worktree recovery**

```python
# src/codogram/handlers/start/launch.py
"""Launch helpers for start flow.

🔴 FIXES applied:
- Silent returns → user feedback messages
- Blocking subprocess.run → asyncio.to_thread
- Race condition → feedback if already launching
- worktree_recovery: pass session_id, reopen topic, restore icon
"""
import asyncio

from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings
from ...core.session_manager import project_manager
from ...services.start import FlowResult
from ...telegram.queue import TelegramQueue
from ...tmux.launcher import is_tmux_session_exists
from .helpers import register_chat_menu


async def launch_claude(msg: Message, result: FlowResult, queue: TelegramQueue):
    """Launch Claude session from message context."""
    from ...telegram.launch_animation import launch_with_animation

    project = project_manager.get_by_chat(msg.chat.id)
    if not project:
        # 🔴 FIX: Was silent return
        await queue.reply(msg, strings.PROJECT_NOT_FOUND, parse_mode=None)
        return

    await register_chat_menu(msg.bot, msg.chat)
    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        # 🔴 FIX: Was silent return
        await queue.reply(msg, strings.LAUNCH_IN_PROGRESS, parse_mode=None)
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=msg.bot, chat_id=msg.chat.id, thread_id=None,
            project=project, thread=thread, queue=queue,
        )
    )


async def launch_claude_from_callback(cb: CallbackQuery, result: FlowResult, queue: TelegramQueue):
    """Launch Claude session from callback context."""
    from ...telegram.launch_animation import launch_with_animation

    project = project_manager.get_by_chat(cb.message.chat.id)
    if not project:
        # 🔴 FIX: Was silent return
        await cb.answer(strings.PROJECT_NOT_FOUND)
        return

    await register_chat_menu(cb.bot, cb.message.chat)
    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        # 🔴 FIX: Was silent return
        await cb.answer(strings.LAUNCH_IN_PROGRESS)
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=cb.bot, chat_id=cb.message.chat.id, thread_id=None,
            project=project, thread=thread, queue=queue,
        )
    )


async def launch_claude_in_thread(msg: Message, result: FlowResult, queue: TelegramQueue):
    """Launch Claude in a specific thread."""
    from ...telegram.launch_animation import launch_with_animation
    from ...tmux.session import TmuxSession
    from ...logging_config import logger

    project = project_manager.get_by_chat(msg.chat.id)
    if not project:
        # 🔴 FIX: Was silent return
        await queue.reply(msg, strings.PROJECT_NOT_FOUND, parse_mode=None)
        return

    thread = project.threads.get(result.thread_id)
    if not thread:
        # 🔴 FIX: Was silent return
        await queue.reply(msg, strings.THREAD_NOT_FOUND, parse_mode=None)
        return

    # Check if tmux already running
    tmux_name = thread.get_tmux_session(project.project_name)
    actual_cwd = thread.worktree_path or project.cwd

    if is_tmux_session_exists(tmux_name):
        tmux = TmuxSession(tmux_name, actual_cwd)
        if tmux.is_claude_ready():
            await queue.reply(msg, strings.START_ALREADY_RUNNING.format(tmux_name=tmux_name))
            return
        else:
            # 🔴 FIX: Was blocking subprocess.run
            import subprocess
            await asyncio.to_thread(
                subprocess.run,
                ["tmux", "kill-session", "-t", tmux_name],
                capture_output=True
            )

    # Reopen topic and reset icon
    if result.thread_id:
        was_reopened = False
        try:
            await msg.bot.reopen_forum_topic(msg.chat.id, result.thread_id)
            logger.info(f"Topic {result.thread_id} reopened")
            was_reopened = True
        except Exception as e:
            # 🟠 FIX: Log instead of bare pass
            logger.debug(f"reopen_forum_topic failed (may be already open): {e}")

        if was_reopened:
            try:
                await msg.bot.edit_forum_topic(
                    msg.chat.id, result.thread_id,
                    icon_custom_emoji_id=strings.ICON_BALLOT_BOX  # 🟠 FIX: Use constant
                )
            except Exception as e:
                logger.warning(f"Failed to set topic icon: {e}")

        if thread.archived:
            thread.archived = False
            project_manager._save()

    if thread.launch_task and not thread.launch_task.done():
        # 🔴 FIX: Was silent return
        await queue.reply(msg, strings.LAUNCH_IN_PROGRESS, parse_mode=None)
        return

    # Check worktree/session validity
    cwd = thread.worktree_path if thread.has_valid_worktree() else None

    session_id = None
    if thread.has_valid_session():
        session_id = thread.session_id
    elif thread.session_id and not thread.has_valid_session():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Start new session",
                                  callback_data=f"resume:start_new:{result.thread_id}")],
            [InlineKeyboardButton(text=strings.BTN_CANCEL,
                                  callback_data=f"resume:cancel:{result.thread_id}")]
        ])
        await queue.reply(msg, strings.START_SESSION_NOT_FOUND, reply_markup=keyboard)
        return

    if thread.worktree_path and not thread.has_valid_worktree():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Recreate worktree",
                                  callback_data=f"resume:recreate:{result.thread_id}")],
            [InlineKeyboardButton(text=strings.BTN_CANCEL,
                                  callback_data=f"resume:cancel:{result.thread_id}")]
        ])
        await queue.reply(msg, strings.START_WORKTREE_NOT_FOUND.format(path=thread.worktree_path),
                          reply_markup=keyboard)
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=msg.bot, chat_id=msg.chat.id, thread_id=result.thread_id,
            project=project, thread=thread, queue=queue,
            session_id=session_id, cwd=cwd,
        )
    )


# === Worktree Recovery Handlers (merged from worktree_recovery.py) ===

async def handle_wr_recreate(callback: CallbackQuery, queue: TelegramQueue):
    """Recreate worktree from existing branch.

    🔴 FIXES: pass session_id, reopen topic, restore icon
    """
    from ...services.branch import create_worktree
    from ...telegram.launch_animation import launch_with_animation
    from ...logging_config import logger

    await callback.answer()
    thread_id = _parse_thread_id(callback.data)
    if thread_id is None:
        await queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
        return

    success, path = create_worktree(Path(project.cwd), thread.name)
    if not success:
        await queue.edit(callback.message, strings.WORKTREE_RECREATE_FAILED.format(path=path))
        return

    thread.worktree_path = path
    project_manager._save()
    await callback.message.delete()

    # 🔴 FIX: Reopen topic and restore icon
    try:
        await callback.bot.reopen_forum_topic(callback.message.chat.id, thread_id)
    except Exception as e:
        logger.debug(f"reopen_forum_topic failed: {e}")

    try:
        await callback.bot.edit_forum_topic(
            callback.message.chat.id, thread_id,
            icon_custom_emoji_id=strings.ICON_BALLOT_BOX
        )
    except Exception as e:
        logger.warning(f"Failed to set topic icon: {e}")

    if thread.archived:
        thread.archived = False
        project_manager._save()

    # 🔴 FIX: Pass session_id if valid
    session_id = thread.session_id if thread.has_valid_session() else None

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot, chat_id=callback.message.chat.id,
            thread_id=thread_id, project=project, thread=thread,
            queue=queue, cwd=path, session_id=session_id,
        )
    )


async def handle_wr_create(callback: CallbackQuery, queue: TelegramQueue):
    """Create new branch and worktree."""
    from ...services.branch import create_branch_with_worktree
    from ...telegram.launch_animation import launch_with_animation
    from ...logging_config import logger

    await callback.answer()
    thread_id = _parse_thread_id(callback.data)
    if thread_id is None:
        await queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
        return

    success, path = create_branch_with_worktree(Path(project.cwd), thread.name)
    if not success:
        await queue.edit(callback.message, strings.WORKTREE_BRANCH_CREATE_FAILED.format(path=path))
        return

    thread.worktree_path = path
    project_manager._save()
    await callback.message.delete()

    # 🔴 FIX: Reopen topic and restore icon
    try:
        await callback.bot.reopen_forum_topic(callback.message.chat.id, thread_id)
    except Exception as e:
        logger.debug(f"reopen_forum_topic failed: {e}")

    try:
        await callback.bot.edit_forum_topic(
            callback.message.chat.id, thread_id,
            icon_custom_emoji_id=strings.ICON_BALLOT_BOX
        )
    except Exception as e:
        logger.warning(f"Failed to set topic icon: {e}")

    if thread.archived:
        thread.archived = False
        project_manager._save()

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot, chat_id=callback.message.chat.id,
            thread_id=thread_id, project=project, thread=thread,
            queue=queue, cwd=path,
        )
    )


async def handle_wr_main(callback: CallbackQuery, queue: TelegramQueue):
    """Resume in main by archiving topic, then launch Claude in main.

    🔴 FIX: Original just archived topic without launching Claude!
    """
    from ...services.branch import archive_thread
    from ...telegram.launch_animation import launch_with_animation

    await callback.answer()
    thread_id = _parse_thread_id(callback.data)
    if thread_id is None:
        await queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
        return

    # Archive the topic
    await archive_thread(callback.bot, callback.message.chat.id, project, thread)
    await queue.edit(callback.message, strings.WORKTREE_TOPIC_ARCHIVED)

    # 🔴 FIX: Launch Claude in main thread
    main_thread = project.get_or_create_thread(None, "main")
    session_id = main_thread.session_id if main_thread.has_valid_session() else None

    main_thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot, chat_id=callback.message.chat.id,
            thread_id=None, project=project, thread=main_thread,
            queue=queue, cwd=project.cwd, session_id=session_id,
        )
    )


async def handle_wr_cancel(callback: CallbackQuery, queue: TelegramQueue):
    """Cancel recovery - just delete message."""
    await callback.answer()
    await callback.message.delete()


def _parse_thread_id(callback_data: str) -> int | None:
    """Parse thread_id from callback data like 'wr_recreate:123'."""
    try:
        return int(callback_data.split(":")[1])
    except (IndexError, ValueError):
        return None
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/start/launch.py
git commit -m "refactor(start): create launch.py with bug fixes"
```

---

## Phase 3: Commands and Callbacks

### Task 10: Create handlers/start/commands.py

**Files:**
- Create: `src/codogram/handlers/start/commands.py`

**Step 1: Create commands.py**

```python
# src/codogram/handlers/start/commands.py
"""Start command handler."""
from pathlib import Path

from aiogram import Router
from aiogram.types import Message
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ...core.session_manager import project_manager
from ...domain.worktree_state import WorktreeState, get_worktree_state
from ...telegram.keyboards.keyboards import worktree_recovery_keyboard
from ...services.start import StartFlowService
from ...telegram.queue import TelegramQueue, OutgoingBatch
from ... import strings
from ..common import normalize_thread_id
from .registry import dispatch_result
from .launch import launch_claude, launch_claude_in_thread

router = Router(name="start_commands")


@router.message(Command("start", ignore_case=True))
async def cmd_start(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle /start command."""
    if message.chat.type == ChatType.PRIVATE:
        return  # DM handled by dm.py

    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    # Check for stale worktree in topic
    if thread_id is not None:
        project = project_manager.get_by_chat(message.chat.id)
        if project:
            thread = project.threads.get(thread_id)
            if thread and thread.worktree_path:
                wt_state = get_worktree_state(thread, Path(project.cwd))
                if wt_state != WorktreeState.OK:
                    try:
                        relative_path = Path(thread.worktree_path).relative_to(Path(project.cwd))
                    except ValueError:
                        relative_path = thread.worktree_path

                    text = (strings.START_WORKTREE_NOT_FOUND_BRANCH_EXISTS
                            if wt_state == WorktreeState.MISSING_WITH_BRANCH
                            else strings.START_WORKTREE_NOT_FOUND_BRANCH_MISSING
                    ).format(path=relative_path, branch=thread.name)

                    batch = OutgoingBatch(
                        chat_id=message.chat.id,
                        thread_id=thread.thread_id,
                        messages=[{"text": text}],
                        reply_markup=worktree_recovery_keyboard(thread.thread_id, wt_state),
                    )
                    await telegram_queue.enqueue(batch)
                    return

    service = StartFlowService(project_manager)
    args = message.text.split()[1:] if message.text else []
    result = service.handle_start(
        chat_id=message.chat.id,
        args=args,
        chat_title=message.chat.title,
        thread_id=thread_id,
    )

    async def launch_cb(msg, res, queue, thread=False):
        if thread:
            await launch_claude_in_thread(msg, res, queue)
        else:
            await launch_claude(msg, res, queue)

    await dispatch_result(message, state, result, telegram_queue, launch_cb)
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/start/commands.py
git commit -m "refactor(start): create commands.py"
```

---

### Task 11-13: Create fsm.py, callbacks.py, assemble router

(Similar structure - extract from original, use new helpers/registry)

---

## Phase 4: Restart Handlers (Simple)

### Task 14: Create handlers/restart/ package

**Files:**
- Create: `src/codogram/handlers/restart/__init__.py`
- Create: `src/codogram/handlers/restart/handlers.py`

**Step 1: Create handlers.py (all restart in one file)**

```python
# src/codogram/handlers/restart/handlers.py
"""Restart handlers - simple, no FlowAction enum."""
import asyncio
from pathlib import Path
import subprocess

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ...core.session_manager import project_manager
from ...domain.states import RestartFlow
from ...services.restart import RestartService
from ...start_flow import restart_confirm_keyboard
from ...telegram.queue import TelegramQueue
from ... import strings
from ..common import normalize_thread_id
from .helpers import parse_callback_data, parse_thread_id

router = Router(name="restart")


@router.message(Command("reset_chat", "restart", ignore_case=True))
async def cmd_restart(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle /restart command."""
    service = RestartService(project_manager)
    thread_id = normalize_thread_id(message.chat, message.message_thread_id)

    tmux_name = service.get_session_to_restart(message.chat.id, thread_id)
    if not tmux_name:
        await telegram_queue.reply(message, strings.NO_SESSION_TO_RESTART, parse_mode=None)
        return

    await state.set_state(RestartFlow.awaiting_confirm)
    await state.update_data(tmux_session=tmux_name, thread_id=thread_id)
    await telegram_queue.reply(
        message,
        strings.START_RESTART_CONFIRM.format(tmux_session=tmux_name),
        reply_markup=restart_confirm_keyboard(),
    )


@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle restart confirmation."""
    data = await state.get_data()
    tmux_session = data.get("tmux_session")
    thread_id = data.get("thread_id")

    if not tmux_session:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    # Cancel background tasks
    project = project_manager.get_by_chat(callback.message.chat.id)
    if project:
        thread = project.get_thread(thread_id)
        if thread:
            for task in [thread.launch_task, thread.watcher_task, thread.poller_task, thread.binding_task]:
                if task and not task.done():
                    task.cancel()

    # Kill session
    service = RestartService(project_manager)
    service.kill_session(tmux_session)

    await state.clear()
    await telegram_queue.edit(callback.message, strings.START_SESSION_KILLED, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle restart cancel."""
    await state.clear()
    await telegram_queue.edit(callback.message, strings.CANCELLED, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("resume:"))
async def on_resume_callback(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle resume error recovery callbacks."""
    # 🔴 FIX: Safe parsing instead of crash
    parts = parse_callback_data(callback.data, 3)
    if not parts:
        await callback.answer("Invalid callback data")
        return

    action = parts[1]
    thread_id = parse_thread_id(parts[2])

    # Validate thread_id if not "cancel"
    if action != "cancel" and parts[2] != "None" and thread_id is None:
        await callback.answer("Invalid thread ID")
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer(strings.PROJECT_NOT_FOUND)
        return

    thread = project.threads.get(thread_id)

    if action == "start_new":
        if thread:
            thread.session_id = None
            thread.jsonl_path = None
            project_manager._save()

        await telegram_queue.edit(callback.message, strings.START_NEW_SESSION)
        await callback.answer()

        from ...telegram.launch_animation import launch_with_animation
        cwd = thread.worktree_path if thread and thread.has_valid_worktree() else None

        if thread:
            thread.launch_task = asyncio.create_task(
                launch_with_animation(
                    bot=callback.bot, chat_id=callback.message.chat.id,
                    thread_id=thread_id, project=project, thread=thread,
                    queue=telegram_queue, cwd=cwd,
                )
            )

    elif action == "recreate":
        if not thread:
            await callback.answer(strings.THREAD_NOT_FOUND)
            return

        # 🔴 FIX: Validate branch_name
        branch_name = thread.name
        if not branch_name:
            await callback.answer("Thread has no branch name")
            return

        await telegram_queue.edit(callback.message, strings.START_RECREATING_WORKTREE)
        await callback.answer()

        main_repo = Path(project.cwd)
        worktree_path = main_repo / ".worktrees" / branch_name

        try:
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=str(main_repo), capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())

            thread.worktree_path = str(worktree_path)
            project_manager._save()
            await telegram_queue.edit(callback.message, strings.START_WORKTREE_RECREATED)
        except Exception as e:
            await telegram_queue.edit(callback.message,
                                      strings.START_WORKTREE_RECREATE_FAILED.format(error=e))

    elif action == "cancel":
        await telegram_queue.edit(callback.message, strings.CANCELLED)
        await callback.answer()
```

**Step 2: Create __init__.py**

```python
# src/codogram/handlers/restart/__init__.py
"""Restart flow handlers."""
from .handlers import router

__all__ = ["router"]
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/restart/
git commit -m "refactor(restart): create simple handlers without FlowAction"
```

---

## Phase 5: Reset Handlers (Simple)

### Task 15: Create handlers/reset/ package

(Similar to restart - one handlers.py file using ResetService)

---

## Phase 6: Integration

### Task 16: Add emoji constants to strings.py

```python
# src/codogram/strings.py - add at top with other constants

# Topic icon emoji IDs (Telegram custom emoji)
ICON_BALLOT_BOX = "5350387571199319521"  # 🗳️ - active topic
ICON_FOLDER = "5357315181649076022"       # 📁 - archived topic
```

### Task 17: Update handlers/__init__.py

```python
# Add imports
from .start import router as start_router
from .restart import router as restart_router
from .reset import router as reset_router

# In register_handlers():
dp.include_router(start_router)
dp.include_router(restart_router)
dp.include_router(reset_router)
```

### Task 18: Delete old files

- Delete: `src/codogram/handlers/start.py`
- Delete: `src/codogram/handlers/worktree_recovery.py` (merged into start/launch.py)
- Update: `src/codogram/handlers/__init__.py` (remove worktree_recovery registration)

### Task 19: Update test imports

### Task 20: Run full test suite + E2E verification

---

## Summary

**Total tasks:** 20

**Key improvements over v1:**
1. Restart/Reset use simple services (no enum)
2. Handler registry replaces god-switch
3. **8 critical bugs fixed** (including worktree_recovery missing session_id/reopen/icon + "Resume in main" no launch)
4. 2 medium bugs fixed
5. **2 low priority fixes** (exception logging, emoji constants)
6. Safer callback data parsing
7. **worktree_recovery.py merged** into handlers/start/launch.py (eliminates duplication)

**Files created:** ~15 new files
**Files deleted:** 2 (old start.py, worktree_recovery.py)
**Estimated LOC per file:** All < 200 LOC
