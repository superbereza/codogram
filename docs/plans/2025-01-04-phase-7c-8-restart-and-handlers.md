# Phase 7c + 8: Restart Flow & Start Handlers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add restart confirmation flow to StartFlowService and wire up all start-related handlers in handlers/start.py

**Architecture:** Phase 7c adds restart-related FlowActions and methods to StartFlowService. Phase 8 creates handlers/start.py that maps FlowResults to Telegram responses using aiogram FSM. Services are injected via middleware.

**Tech Stack:** Python, aiogram 3.x FSM, pytest

---

## Background

### Current State
- `StartFlowService` in `services/start_flow.py` handles all /start business logic
- `_start_state` dict in bot.py manages conversation state (to be replaced with aiogram FSM)
- Handlers are scattered in bot.py (~500+ lines of start-related code)
- `handlers/permissions.py` shows the pattern for handler modules

### Target State
- Restart flow uses `FlowAction.ASK_RESTART_CONFIRM` / `RESTART_DONE` / `CANCELLED`
- `handlers/start.py` contains all /start and /restart handlers
- aiogram FSM replaces `_start_state` dict
- Services injected via `start_flow: StartFlowService` parameter

### Key Files
- `src/codogram/services/start_flow.py` - add restart methods
- `src/codogram/domain/states.py` - add RestartFlow FSM
- `src/codogram/handlers/start.py` - NEW: all start/restart handlers
- `src/codogram/handlers/__init__.py` - register start router
- `tests/test_start_flow_service.py` - add restart tests
- `tests/test_handlers_start.py` - NEW: handler tests

---

## Phase 7c: Restart Confirmation Flow

### Task 1: Add restart FlowActions

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestRestartFlowActions:
    """Tests for restart-related FlowActions."""

    def test_has_ask_restart_confirm(self):
        """FlowAction.ASK_RESTART_CONFIRM exists."""
        assert hasattr(FlowAction, "ASK_RESTART_CONFIRM")

    def test_has_restart_done(self):
        """FlowAction.RESTART_DONE exists."""
        assert hasattr(FlowAction, "RESTART_DONE")

    def test_has_cancelled(self):
        """FlowAction.CANCELLED exists."""
        assert hasattr(FlowAction, "CANCELLED")
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestRestartFlowActions -v
```

Expected: FAIL with `AttributeError`

**Step 3: Add FlowActions**

In `src/codogram/services/start_flow.py`, add to `FlowAction` enum:

```python
class FlowAction(Enum):
    # ... existing actions ...

    # Restart flow
    ASK_RESTART_CONFIRM = "ask_restart_confirm"
    RESTART_DONE = "restart_done"
    CANCELLED = "cancelled"
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestRestartFlowActions -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add restart FlowActions"
```

---

### Task 2: Add RestartFlow FSM state

**Files:**
- Modify: `src/codogram/domain/states.py`
- Create: `tests/test_states.py`

**Step 1: Write the failing test**

Create `tests/test_states.py`:

```python
"""Tests for FSM states."""
from codogram.domain.states import StartFlow, RestartFlow


class TestRestartFlow:
    """Tests for RestartFlow FSM."""

    def test_has_awaiting_confirm(self):
        """RestartFlow.awaiting_confirm exists."""
        assert hasattr(RestartFlow, "awaiting_confirm")
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=src pytest tests/test_states.py::TestRestartFlow -v
```

Expected: FAIL with `ImportError: cannot import name 'RestartFlow'`

**Step 3: Add RestartFlow**

In `src/codogram/domain/states.py`:

```python
"""FSM states for conversation flows."""
from aiogram.fsm.state import State, StatesGroup


class StartFlow(StatesGroup):
    """States for /start command flow."""
    awaiting_project_name = State()
    awaiting_dir_choice = State()
    awaiting_git_choice = State()
    awaiting_gh_visibility = State()
    awaiting_clone_url = State()
    awaiting_custom_path = State()
    awaiting_launch_confirm = State()


class RestartFlow(StatesGroup):
    """States for /restart confirmation flow."""
    awaiting_confirm = State()
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=src pytest tests/test_states.py::TestRestartFlow -v
```

**Step 5: Commit**

```bash
git add src/codogram/domain/states.py tests/test_states.py
git commit -m "feat(states): add RestartFlow FSM state"
```

---

### Task 3: Add handle_restart method

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleRestart:
    """Tests for restart flow."""

    def test_handle_restart_no_project(self):
        """No project -> ERROR."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_restart(chat_id=123, thread_id=None)

        assert result.action == FlowAction.ERROR
        assert "No active session" in result.error

    def test_handle_restart_no_tmux(self):
        """Project exists but no tmux -> ERROR."""
        mock_pm = Mock()
        project = Mock(project_name="test", tmux_session=None, threads={})
        mock_pm.get_by_chat.return_value = project

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_restart(chat_id=123, thread_id=None)

        assert result.action == FlowAction.ERROR

    def test_handle_restart_tmux_exists(self):
        """Project with tmux -> ASK_RESTART_CONFIRM."""
        mock_pm = Mock()
        project = Mock(
            project_name="test",
            tmux_session="test-main",
            threads={},
        )
        mock_pm.get_by_chat.return_value = project

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.is_tmux_session_exists") as mock_exists:
            mock_exists.return_value = True
            result = service.handle_restart(chat_id=123, thread_id=None)

        assert result.action == FlowAction.ASK_RESTART_CONFIRM
        assert result.project == "test"
        assert result.tmux_session == "test-main"

    def test_handle_restart_thread_mode(self):
        """Thread mode uses thread's tmux."""
        mock_pm = Mock()
        thread = Mock()
        thread.thread_id = 456
        thread.get_tmux_session.return_value = "test-mystic"
        project = Mock(
            project_name="test",
            threads={456: thread},
        )
        mock_pm.get_by_chat.return_value = project

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.is_tmux_session_exists") as mock_exists:
            mock_exists.return_value = True
            result = service.handle_restart(chat_id=123, thread_id=456)

        assert result.action == FlowAction.ASK_RESTART_CONFIRM
        assert result.tmux_session == "test-mystic"
        assert result.thread_id == 456
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleRestart -v
```

Expected: FAIL with `AttributeError: 'StartFlowService' object has no attribute 'handle_restart'`

**Step 3: Implement handle_restart**

Add to `src/codogram/services/start_flow.py`:

```python
def handle_restart(
    self, chat_id: int, thread_id: int | None = None
) -> FlowResult:
    """Handle /restart command.

    Args:
        chat_id: Telegram chat ID
        thread_id: Topic thread ID (None for main chat)

    Returns:
        FlowResult with ASK_RESTART_CONFIRM or ERROR
    """
    project = self.pm.get_by_chat(chat_id)
    if not project:
        return FlowResult(
            action=FlowAction.ERROR,
            error="No active session to restart.",
        )

    # Determine tmux session
    if thread_id:
        thread = project.threads.get(thread_id)
        if not thread:
            return FlowResult(
                action=FlowAction.ERROR,
                error="No active session to restart.",
            )
        tmux_name = thread.get_tmux_session(project.project_name)
    else:
        # Main thread or legacy
        main_thread = project.threads.get(None)
        if main_thread:
            tmux_name = main_thread.get_tmux_session(project.project_name)
        elif project.tmux_session:
            tmux_name = project.tmux_session
        else:
            return FlowResult(
                action=FlowAction.ERROR,
                error="No active session to restart.",
            )

    # Check tmux exists
    if not is_tmux_session_exists(tmux_name):
        return FlowResult(
            action=FlowAction.ERROR,
            error="No active session to restart.",
        )

    return FlowResult(
        action=FlowAction.ASK_RESTART_CONFIRM,
        project=project.project_name,
        tmux_session=tmux_name,
        thread_id=thread_id,
    )
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleRestart -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add handle_restart method"
```

---

### Task 4: Add handle_restart_confirm and handle_cancel methods

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleRestartConfirm:
    """Tests for restart confirmation."""

    def test_handle_restart_confirm(self):
        """Confirm -> RESTART_DONE."""
        mock_pm = Mock()
        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.kill_tmux_session") as mock_kill:
            mock_kill.return_value = True
            result = service.handle_restart_confirm(tmux_session="test-main")

        assert result.action == FlowAction.RESTART_DONE
        mock_kill.assert_called_once_with("test-main")

    def test_handle_cancel(self):
        """Cancel -> CANCELLED."""
        mock_pm = Mock()
        service = StartFlowService(mock_pm, Mock())

        result = service.handle_cancel()

        assert result.action == FlowAction.CANCELLED
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleRestartConfirm -v
```

Expected: FAIL with `AttributeError`

**Step 3: Add kill_tmux_session import and implement methods**

First, check if `kill_tmux_session` exists in tmux.py. If not, add it:

In `src/codogram/tmux.py` (if not present):

```python
def kill_tmux_session(session_name: str) -> bool:
    """Kill a tmux session by name."""
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False
```

Add import to `src/codogram/services/start_flow.py`:

```python
from ..tmux import find_all_tmux_by_cwd, find_tmux_by_convention, TmuxSession, kill_tmux_session
```

Add methods:

```python
def handle_restart_confirm(self, tmux_session: str) -> FlowResult:
    """Handle restart confirmation - kill tmux session."""
    kill_tmux_session(tmux_session)
    return FlowResult(action=FlowAction.RESTART_DONE)

def handle_cancel(self) -> FlowResult:
    """Handle cancel button."""
    return FlowResult(action=FlowAction.CANCELLED)
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleRestartConfirm -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py src/codogram/tmux.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add handle_restart_confirm and handle_cancel"
```

---

## Phase 8: handlers/start.py

### Task 5: Create handlers/start.py skeleton with /start command

**Files:**
- Create: `src/codogram/handlers/start.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Create handlers/start.py with /start command**

Create `src/codogram/handlers/start.py`:

```python
"""Start flow handlers - /start, /restart and related callbacks."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..domain.states import StartFlow, RestartFlow
from ..services.start_flow import StartFlowService, FlowAction, FlowResult
from ..session_manager import project_manager
from ..start_flow import (
    dir_not_found_keyboard,
    git_setup_keyboard,
    git_visibility_keyboard,
    restart_confirm_keyboard,
)
from ..tmux_selector import create_tmux_selection_keyboard

router = Router(name="start")


# ===== Result Handlers =====

async def _handle_result(
    message: Message,
    state: FSMContext,
    result: FlowResult,
    start_flow: StartFlowService,
):
    """Map FlowResult to Telegram response for messages."""
    match result.action:
        case FlowAction.ASK_PROJECT_NAME:
            await state.set_state(StartFlow.awaiting_project_name)
            if result.thread_id:
                await state.update_data(thread_id=result.thread_id)
            await message.answer("Отправь имя проекта:")

        case FlowAction.ASK_DIR_CHOICE:
            await state.set_state(StartFlow.awaiting_dir_choice)
            await state.update_data(project=result.project, path=result.path)
            await message.answer(
                f"Директория `{result.path}` не найдена.\n\nЧто делать?",
                reply_markup=dir_not_found_keyboard(),
                parse_mode="Markdown",
            )

        case FlowAction.ASK_GIT_CHOICE:
            await state.set_state(StartFlow.awaiting_git_choice)
            await state.update_data(project=result.project, path=result.path)
            await message.answer(
                "Git setup?",
                reply_markup=git_setup_keyboard(),
            )

        case FlowAction.ASK_LAUNCH_CONFIRM:
            await state.set_state(StartFlow.awaiting_launch_confirm)
            await state.update_data(project=result.project, path=result.path)
            from ..keyboards.start import launch_confirm_keyboard
            await message.answer(
                f"Запустить Claude в `{result.path}`?",
                reply_markup=launch_confirm_keyboard(),
                parse_mode="Markdown",
            )

        case FlowAction.SHOW_STATUS:
            await state.clear()
            await message.answer(
                f"Claude running: `{result.project}` in `{result.tmux_session}`",
                parse_mode="Markdown",
            )

        case FlowAction.CONNECT:
            await state.clear()
            await _connect_to_session(message, result)

        case FlowAction.LAUNCH:
            await state.clear()
            await _launch_claude(message, result)

        case FlowAction.SELECT_TMUX:
            await message.answer(
                "Multiple tmux sessions found. Select one:",
                reply_markup=create_tmux_selection_keyboard(
                    result.project, result.tmux_list
                ),
            )

        case FlowAction.ERROR:
            await state.clear()
            await message.answer(f"Error: {result.error}")

        case FlowAction.CANCELLED:
            await state.clear()
            await message.answer("Cancelled.")

        # Thread-specific actions
        case FlowAction.THREAD_SHOW_STATUS:
            await state.clear()
            await message.answer(
                f"Thread `{result.thread_name}` running in `{result.tmux_session}`",
                parse_mode="Markdown",
            )

        case FlowAction.THREAD_LAUNCH:
            await state.clear()
            await _launch_claude_in_thread(message, result)

        case FlowAction.UPGRADE_PENDING_THREAD:
            await state.clear()
            await message.answer(
                f"Thread upgraded to `{result.thread_name}`",
                parse_mode="Markdown",
            )
            await _launch_claude_in_thread(message, result)

        case FlowAction.REGISTER_UNKNOWN_TOPIC:
            await state.clear()
            await message.answer(
                f"Topic registered as `{result.thread_name}`",
                parse_mode="Markdown",
            )
            await _launch_claude_in_thread(message, result)


async def _handle_callback_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: FlowResult,
    start_flow: StartFlowService,
):
    """Map FlowResult to Telegram response for callbacks."""
    await callback.answer()

    match result.action:
        case FlowAction.ASK_GIT_CHOICE:
            await state.set_state(StartFlow.awaiting_git_choice)
            await state.update_data(project=result.project, path=result.path)
            await callback.message.edit_text(
                "Git setup?",
                reply_markup=git_setup_keyboard(),
            )

        case FlowAction.LAUNCH:
            await state.clear()
            await callback.message.edit_text("Launching Claude...")
            await _launch_claude_from_callback(callback, result)

        case FlowAction.CONNECT:
            await state.clear()
            await callback.message.edit_text(f"Connected to `{result.tmux_session}`", parse_mode="Markdown")
            await _connect_to_session_from_callback(callback, result)

        case FlowAction.ERROR:
            await state.clear()
            await callback.message.edit_text(f"Error: {result.error}")

        case FlowAction.RESTART_DONE:
            await state.clear()
            await callback.message.edit_text("Session killed. Use /start to restart.")

        case FlowAction.CANCELLED:
            await state.clear()
            await callback.message.edit_text("Cancelled.")


# ===== Launch Helpers =====

async def _launch_claude(message: Message, result: FlowResult):
    """Launch Claude session from message context."""
    from ..launch_animation import launch_with_animation
    from ..main import telegram_queue
    import asyncio

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Project not found")
        return

    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        await message.answer("Launch already in progress")
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )


async def _launch_claude_from_callback(callback: CallbackQuery, result: FlowResult):
    """Launch Claude session from callback context."""
    from ..launch_animation import launch_with_animation
    from ..main import telegram_queue
    import asyncio

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        return

    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )


async def _launch_claude_in_thread(message: Message, result: FlowResult):
    """Launch Claude in a specific thread."""
    from ..launch_animation import launch_with_animation
    from ..main import telegram_queue
    import asyncio

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        return

    thread = project.threads.get(result.thread_id)
    if not thread:
        return

    if thread.launch_task and not thread.launch_task.done():
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=result.thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )


async def _connect_to_session(message: Message, result: FlowResult):
    """Connect to existing tmux session."""
    # Start pollers for the session
    project = project_manager.get_by_chat(message.chat.id)
    if project:
        project.tmux_session = result.tmux_session
        project_manager._save()
        # TODO: Start pollers
        await message.answer(f"Connected to `{result.tmux_session}`", parse_mode="Markdown")


async def _connect_to_session_from_callback(callback: CallbackQuery, result: FlowResult):
    """Connect to existing tmux session from callback."""
    project = project_manager.get_by_chat(callback.message.chat.id)
    if project:
        project.tmux_session = result.tmux_session
        project_manager._save()
```

**Step 2: Update handlers/__init__.py**

```python
"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start


def register_handlers(dp: Dispatcher):
    """Register all handler routers.

    Note: All routers are protected by AdminMiddleware on dp level.
    No need to add middleware to individual routers.
    """
    dp.include_router(permissions.router)
    dp.include_router(start.router)
```

**Step 3: Verify import works**

```bash
PYTHONPATH=src python -c "from codogram.handlers.start import router; print('OK')"
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/start.py src/codogram/handlers/__init__.py
git commit -m "feat(handlers): add start.py skeleton with result handlers"
```

---

### Task 6: Add /start command handler

**Files:**
- Modify: `src/codogram/handlers/start.py`
- Create: `tests/test_handlers_start.py`

**Step 1: Add /start handler to handlers/start.py**

Add to `src/codogram/handlers/start.py` after result handlers:

```python
# ===== Commands =====

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    # Create service (TODO: inject via middleware)
    start_flow = StartFlowService(project_manager, None)

    args = message.text.split()[1:] if message.text else []
    thread_id = message.message_thread_id

    result = start_flow.handle_start(
        chat_id=message.chat.id,
        args=args,
        chat_title=message.chat.title,
        thread_id=thread_id,
    )

    await _handle_result(message, state, result, start_flow)
```

**Step 2: Write basic test**

Create `tests/test_handlers_start.py`:

```python
"""Tests for start handlers."""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from aiogram.types import Message, Chat, User
from aiogram.fsm.context import FSMContext

from codogram.handlers.start import cmd_start
from codogram.services.start_flow import FlowAction


@pytest.fixture
def mock_message():
    """Create mock message."""
    message = Mock(spec=Message)
    message.chat = Mock(spec=Chat)
    message.chat.id = 123
    message.chat.title = "Test Chat"
    message.text = "/start"
    message.message_thread_id = None
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_state():
    """Create mock FSM state."""
    state = Mock(spec=FSMContext)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


class TestCmdStart:
    """Tests for /start command."""

    @pytest.mark.asyncio
    async def test_start_no_project_asks_name(self, mock_message, mock_state):
        """No project -> asks for project name."""
        with patch("codogram.handlers.start.project_manager") as mock_pm:
            mock_pm.get_by_chat.return_value = None

            await cmd_start(mock_message, mock_state)

        mock_state.set_state.assert_called_once()
        mock_message.answer.assert_called_once()
        assert "имя проекта" in mock_message.answer.call_args[0][0].lower() or \
               "project" in mock_message.answer.call_args[0][0].lower()
```

**Step 3: Run test**

```bash
PYTHONPATH=src pytest tests/test_handlers_start.py -v
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/start.py tests/test_handlers_start.py
git commit -m "feat(handlers): add /start command handler"
```

---

### Task 7: Add FSM state handlers for project name and custom path

**Files:**
- Modify: `src/codogram/handlers/start.py`

**Step 1: Add FSM handlers**

Add to `src/codogram/handlers/start.py`:

```python
# ===== FSM State Handlers =====

@router.message(StartFlow.awaiting_project_name)
async def on_project_name(message: Message, state: FSMContext):
    """Handle project name input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    thread_id = data.get("thread_id")

    result = start_flow.handle_project_name(message.chat.id, message.text.strip())

    # If thread flow, preserve thread_id
    if thread_id and result.thread_id is None:
        result.thread_id = thread_id

    await _handle_result(message, state, result, start_flow)


@router.message(StartFlow.awaiting_custom_path)
async def on_custom_path(message: Message, state: FSMContext):
    """Handle custom path input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_custom_path(
        message.chat.id,
        data["project"],
        message.text.strip(),
    )

    await _handle_result(message, state, result, start_flow)


@router.message(StartFlow.awaiting_clone_url)
async def on_clone_url(message: Message, state: FSMContext):
    """Handle git clone URL input."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_clone_url(
        message.chat.id,
        data["project"],
        data["path"],
        message.text.strip(),
    )

    await _handle_result(message, state, result, start_flow)
```

**Step 2: Verify no syntax errors**

```bash
PYTHONPATH=src python -c "from codogram.handlers.start import router; print('OK')"
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/start.py
git commit -m "feat(handlers): add FSM state handlers for project name, custom path, clone URL"
```

---

### Task 8: Add callback handlers for directory and git choices

**Files:**
- Modify: `src/codogram/handlers/start.py`

**Step 1: Add callback handlers**

Add to `src/codogram/handlers/start.py`:

```python
# ===== Callback Handlers =====

@router.callback_query(F.data == "start:create_dir")
async def on_create_dir(callback: CallbackQuery, state: FSMContext):
    """Handle create directory button."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_create_dir(data["project"], data["path"])

    await _handle_callback_result(callback, state, result, start_flow)


@router.callback_query(F.data == "start:custom_path")
async def on_custom_path_btn(callback: CallbackQuery, state: FSMContext):
    """Handle custom path button."""
    await state.set_state(StartFlow.awaiting_custom_path)
    await callback.message.edit_text("Отправь путь к директории:")
    await callback.answer()


@router.callback_query(F.data == "start:git_init")
async def on_git_init(callback: CallbackQuery, state: FSMContext):
    """Handle git init button."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_git_init(
        callback.message.chat.id,
        data["project"],
        data["path"],
    )

    await _handle_callback_result(callback, state, result, start_flow)


@router.callback_query(F.data == "start:git_gh")
async def on_git_gh(callback: CallbackQuery, state: FSMContext):
    """Handle git + gh button."""
    await state.set_state(StartFlow.awaiting_gh_visibility)
    await callback.message.edit_text(
        "Видимость репозитория?",
        reply_markup=git_visibility_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"start:gh_private", "start:gh_public"}))
async def on_gh_visibility(callback: CallbackQuery, state: FSMContext):
    """Handle GitHub visibility choice."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    private = callback.data == "start:gh_private"
    result = start_flow.handle_gh_create(
        callback.message.chat.id,
        data["project"],
        data["path"],
        private,
    )

    await _handle_callback_result(callback, state, result, start_flow)


@router.callback_query(F.data == "start:git_clone")
async def on_git_clone(callback: CallbackQuery, state: FSMContext):
    """Handle git clone button."""
    await state.set_state(StartFlow.awaiting_clone_url)
    await callback.message.edit_text("Отправь ссылку на репозиторий:")
    await callback.answer()


@router.callback_query(F.data == "start:no_git")
async def on_no_git(callback: CallbackQuery, state: FSMContext):
    """Handle no git button."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    result = start_flow.handle_no_git(
        callback.message.chat.id,
        data["project"],
        data["path"],
    )

    await _handle_callback_result(callback, state, result, start_flow)


@router.callback_query(F.data == "start:launch_claude")
async def on_launch_claude(callback: CallbackQuery, state: FSMContext):
    """Handle launch Claude button."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()

    # Get project and launch
    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Project not found")
        return

    await state.clear()
    await callback.message.edit_text("Launching Claude...")
    await callback.answer()

    result = FlowResult(
        action=FlowAction.LAUNCH,
        project=data["project"],
        path=data["path"],
    )
    await _launch_claude_from_callback(callback, result)


@router.callback_query(F.data == "start:cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext):
    """Handle cancel button."""
    await state.clear()
    await callback.message.edit_text("Cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("select_tmux:"))
async def on_tmux_selected(callback: CallbackQuery, state: FSMContext):
    """Handle tmux selection."""
    start_flow = StartFlowService(project_manager, None)

    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid callback")
        return

    project_name, tmux_session = parts[1], parts[2]
    result = start_flow.handle_tmux_selected(
        callback.message.chat.id,
        project_name,
        tmux_session,
    )

    await _handle_callback_result(callback, state, result, start_flow)
```

**Step 2: Verify no syntax errors**

```bash
PYTHONPATH=src python -c "from codogram.handlers.start import router; print('OK')"
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/start.py
git commit -m "feat(handlers): add callback handlers for directory and git choices"
```

---

### Task 9: Add /restart command and callbacks

**Files:**
- Modify: `src/codogram/handlers/start.py`

**Step 1: Add /restart handlers**

Add to `src/codogram/handlers/start.py`:

```python
# ===== Restart Flow =====

@router.message(Command("restart"))
async def cmd_restart(message: Message, state: FSMContext):
    """Handle /restart command."""
    start_flow = StartFlowService(project_manager, None)

    result = start_flow.handle_restart(
        chat_id=message.chat.id,
        thread_id=message.message_thread_id,
    )

    if result.action == FlowAction.ASK_RESTART_CONFIRM:
        await state.set_state(RestartFlow.awaiting_confirm)
        await state.update_data(tmux_session=result.tmux_session)
        await message.answer(
            f"Restart session `{result.tmux_session}`?",
            reply_markup=restart_confirm_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await _handle_result(message, state, result, start_flow)


@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery, state: FSMContext):
    """Handle restart confirmation."""
    start_flow = StartFlowService(project_manager, None)

    data = await state.get_data()
    tmux_session = data.get("tmux_session")

    if not tmux_session:
        await callback.answer("Session expired")
        return

    result = start_flow.handle_restart_confirm(tmux_session)

    await _handle_callback_result(callback, state, result, start_flow)


@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery, state: FSMContext):
    """Handle restart cancel."""
    start_flow = StartFlowService(project_manager, None)

    result = start_flow.handle_cancel()

    await _handle_callback_result(callback, state, result, start_flow)
```

**Step 2: Verify no syntax errors**

```bash
PYTHONPATH=src python -c "from codogram.handlers.start import router; print('OK')"
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/start.py
git commit -m "feat(handlers): add /restart command and callbacks"
```

---

### Task 10: Add launch_confirm_keyboard

**Files:**
- Modify: `src/codogram/start_flow.py` (keyboards file)

**Step 1: Add keyboard function**

Add to `src/codogram/start_flow.py`:

```python
def launch_confirm_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for launch confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Launch Claude", callback_data="start:launch_claude"),
            InlineKeyboardButton(text="Cancel", callback_data="start:cancel"),
        ]
    ])
```

**Step 2: Verify import works**

```bash
PYTHONPATH=src python -c "from codogram.start_flow import launch_confirm_keyboard; print('OK')"
```

**Step 3: Update handlers/start.py import**

In `src/codogram/handlers/start.py`, update import:

```python
from ..start_flow import (
    dir_not_found_keyboard,
    git_setup_keyboard,
    git_visibility_keyboard,
    restart_confirm_keyboard,
    launch_confirm_keyboard,
)
```

And update `_handle_result` to use direct import instead of lazy import.

**Step 4: Commit**

```bash
git add src/codogram/start_flow.py src/codogram/handlers/start.py
git commit -m "feat(keyboards): add launch_confirm_keyboard"
```

---

### Task 11: Final verification

**Files:**
- All files from previous tasks

**Step 1: Run all Phase 7c tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py -v -k "Restart"
```

Expected: All restart-related tests PASS

**Step 2: Run all handler tests**

```bash
PYTHONPATH=src pytest tests/test_handlers_start.py -v
```

Expected: All handler tests PASS

**Step 3: Run full test suite**

```bash
PYTHONPATH=src pytest tests/ -v
```

Expected: All tests PASS (no regressions)

**Step 4: Verify imports**

```bash
PYTHONPATH=src python -c "
from codogram.handlers.start import router, cmd_start, cmd_restart
from codogram.services.start_flow import FlowAction
from codogram.domain.states import StartFlow, RestartFlow
print('All imports OK')
print('FlowActions:', [a.name for a in FlowAction if 'RESTART' in a.name or 'CANCEL' in a.name])
print('RestartFlow states:', [s for s in dir(RestartFlow) if not s.startswith('_')])
"
```

**Step 5: Commit any cleanup**

```bash
git status
# If any uncommitted changes:
git add -A
git commit -m "chore: cleanup Phase 7c + 8 implementation"
```

---

## Summary

**Phase 7c additions to StartFlowService:**
- `FlowAction.ASK_RESTART_CONFIRM` / `RESTART_DONE` / `CANCELLED`
- `handle_restart(chat_id, thread_id)` - initiate restart flow
- `handle_restart_confirm(tmux_session)` - execute restart
- `handle_cancel()` - cancel any flow

**Phase 8 handlers/start.py:**
- `/start` command with thread_id support
- `/restart` command with confirmation flow
- FSM state handlers: project_name, custom_path, clone_url
- Callback handlers: create_dir, git_init, git_gh, gh_visibility, git_clone, no_git, launch_claude, cancel, tmux_selected
- Restart callbacks: restart:confirm, restart:cancel
- Result handlers: `_handle_result`, `_handle_callback_result`
- Launch helpers: `_launch_claude`, `_launch_claude_from_callback`, `_launch_claude_in_thread`

**New files:**
- `src/codogram/handlers/start.py`
- `tests/test_handlers_start.py`
- `tests/test_states.py`

**Modified files:**
- `src/codogram/services/start_flow.py` - restart methods
- `src/codogram/domain/states.py` - RestartFlow
- `src/codogram/handlers/__init__.py` - register start router
- `src/codogram/start_flow.py` - launch_confirm_keyboard

---

## Handler Behavior (Phase 8)

When handlers are wired up, bot.py /start code can be gradually removed. The handler uses:
1. `StartFlowService` for business logic
2. aiogram FSM for state management
3. `_handle_result` / `_handle_callback_result` for response mapping

The service returns `FlowResult`, handler maps it to Telegram response.

## Notes

- **Dependency Injection**: Currently handlers create `StartFlowService(project_manager, None)` inline. Future improvement: inject via middleware.
- **kill_tmux_session**: May already exist in tmux.py. Check before adding.
- **Thread support**: All handlers respect `message.message_thread_id` and `result.thread_id`.
