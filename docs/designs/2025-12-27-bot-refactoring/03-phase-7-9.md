# Фазы 7-9: FSM, Start, Sessions

## Фаза 7: Вынести services/start_flow.py + FSM

**Цель:** Чистая FSM логика, отделённая от Telegram handlers

### Анализ текущего flow

```
_start_state dict хранит:
{
    chat_id: {
        "state": "awaiting_project_name" | "awaiting_dir_choice" | ...,
        "project": str,
        "path": str,
    }
}

Переходы:
/start
  → есть args? → _start_project_flow()
  → нет project? → "awaiting_project_name"
  → есть project? → _start_project_flow()

_start_project_flow()
  → path exists? → _connect_or_launch()
  → path not exists? → "awaiting_dir_choice"

awaiting_dir_choice
  → create_dir → "awaiting_git_choice"
  → custom_path → "awaiting_custom_path"

awaiting_git_choice
  → git_init → launch
  → git_gh → "awaiting_gh_visibility"
  → git_clone → "awaiting_clone_url"
  → no_git → launch
```

### Шаги

#### 7.1 domain/states.py (уже создан в фазе 2)

```python
from aiogram.fsm.state import State, StatesGroup

class StartFlow(StatesGroup):
    awaiting_project_name = State()
    awaiting_dir_choice = State()
    awaiting_git_choice = State()
    awaiting_gh_visibility = State()
    awaiting_clone_url = State()
    awaiting_custom_path = State()
    awaiting_launch_confirm = State()
```

#### 7.2 services/start_flow.py

```python
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

from ..domain.validators import is_valid_project_name
from ..project_launcher import resolve_project_path
from ..session_manager import project_manager

class FlowAction(Enum):
    ASK_PROJECT_NAME = "ask_project_name"
    ASK_DIR_CHOICE = "ask_dir_choice"
    ASK_GIT_CHOICE = "ask_git_choice"
    ASK_GH_VISIBILITY = "ask_gh_visibility"
    ASK_CLONE_URL = "ask_clone_url"
    ASK_LAUNCH_CONFIRM = "ask_launch_confirm"
    SHOW_STATUS = "show_status"
    LAUNCH = "launch"
    CONNECT = "connect"
    SELECT_TMUX = "select_tmux"
    ERROR = "error"

@dataclass
class FlowResult:
    action: FlowAction
    project: str | None = None
    path: str | None = None
    tmux_list: list[str] | None = None
    message: str | None = None
    error: str | None = None

class StartFlowService:
    """Business logic for /start flow."""

    def __init__(self, project_manager, launch_service):
        self.pm = project_manager
        self.launch = launch_service

    def handle_start(
        self,
        chat_id: int,
        args: list[str],
        chat_title: str | None = None,
    ) -> FlowResult:
        """Entry point for /start command."""

        # Case 1: project name provided
        if args:
            project_name = args[0]
            if not is_valid_project_name(project_name):
                return FlowResult(
                    action=FlowAction.ERROR,
                    error="Имя проекта может содержать только буквы, цифры, - и _"
                )
            return self._start_project_flow(chat_id, project_name)

        # Case 2: existing project for chat
        project = self.pm.get_by_chat(chat_id)
        if project:
            if self._is_claude_running(project):
                return FlowResult(
                    action=FlowAction.SHOW_STATUS,
                    project=project.project_name,
                    path=project.cwd,
                )
            return self._start_project_flow(chat_id, project.project_name)

        # Case 3: use chat title
        if chat_title:
            sanitized = self._sanitize_project_name(chat_title)
            if sanitized:
                return self._start_project_flow(chat_id, sanitized)

        # Case 4: ask for project name
        return FlowResult(action=FlowAction.ASK_PROJECT_NAME)

    def _start_project_flow(self, chat_id: int, project_name: str) -> FlowResult:
        """Resolve path and decide next step."""
        project = self.pm.get_or_create(project_name)
        project.chat_id = chat_id

        if project.cwd:
            path = project.cwd
            exists = Path(path).is_dir()
        else:
            path_result = resolve_project_path(project_name, None)
            path = path_result.path
            exists = path_result.exists

        if exists:
            project.cwd = path
            return self._connect_or_launch(project)
        else:
            return FlowResult(
                action=FlowAction.ASK_DIR_CHOICE,
                project=project_name,
                path=path,
            )

    def _connect_or_launch(self, project) -> FlowResult:
        """Find tmux or offer to create."""
        from ..tmux import find_all_tmux_by_cwd, find_tmux_by_convention

        tmux_list = find_all_tmux_by_cwd(project.cwd)

        if len(tmux_list) == 0:
            tmux = find_tmux_by_convention(project.project_name)
            if tmux:
                project.tmux_session = tmux
                return FlowResult(
                    action=FlowAction.CONNECT,
                    project=project.project_name,
                )
            else:
                return FlowResult(
                    action=FlowAction.ASK_LAUNCH_CONFIRM,
                    project=project.project_name,
                    path=project.cwd,
                )
        elif len(tmux_list) == 1:
            project.tmux_session = tmux_list[0]
            return FlowResult(
                action=FlowAction.CONNECT,
                project=project.project_name,
            )
        else:
            return FlowResult(
                action=FlowAction.SELECT_TMUX,
                project=project.project_name,
                tmux_list=tmux_list,
            )

    def handle_project_name(self, chat_id: int, name: str) -> FlowResult:
        """Handle user input for project name."""
        if not is_valid_project_name(name):
            return FlowResult(
                action=FlowAction.ERROR,
                error="Имя проекта может содержать только буквы, цифры, - и _"
            )
        return self._start_project_flow(chat_id, name)

    def handle_custom_path(self, chat_id: int, project: str, path: str) -> FlowResult:
        """Handle user input for custom path."""
        expanded = Path(path).expanduser()
        if not expanded.is_dir():
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"Директория {path} не существует"
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = str(expanded)
        self.pm._save()

        return FlowResult(action=FlowAction.LAUNCH, project=project, path=str(expanded))

    def _is_claude_running(self, project) -> bool:
        """Check if Claude is running for project."""
        from ..project_launcher import is_tmux_session_exists

        if not project.tmux_session:
            return False
        if not is_tmux_session_exists(project.tmux_session):
            return False
        if not project.poller_task or project.poller_task.done():
            return False
        if not project.watcher_task or project.watcher_task.done():
            return False
        return True

    def _sanitize_project_name(self, title: str) -> str | None:
        """Convert chat title to valid project name."""
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', title)
        sanitized = re.sub(r'-+', '-', sanitized).strip('-')
        if sanitized and is_valid_project_name(sanitized):
            return sanitized
        return None
```

#### 7.3 Handler использует service + FSM

```python
# handlers/start.py
from aiogram.fsm.context import FSMContext
from ..domain.states import StartFlow
from ..services.start_flow import StartFlowService, FlowResult, FlowAction

@router.message(Command("start"))
async def cmd_start(
    message: Message,
    state: FSMContext,
    start_flow: StartFlowService,
):
    args = message.text.split()[1:]
    result = start_flow.handle_start(
        chat_id=message.chat.id,
        args=args,
        chat_title=message.chat.title,
    )
    await _handle_flow_result(message, state, result)

@router.message(StartFlow.awaiting_project_name)
async def on_project_name(
    message: Message,
    state: FSMContext,
    start_flow: StartFlowService,
):
    result = start_flow.handle_project_name(
        chat_id=message.chat.id,
        name=message.text.strip(),
    )
    await _handle_flow_result(message, state, result)

async def _handle_flow_result(
    message: Message,
    state: FSMContext,
    result: FlowResult,
):
    """Convert FlowResult to Telegram response."""
    match result.action:
        case FlowAction.ASK_PROJECT_NAME:
            await state.set_state(StartFlow.awaiting_project_name)
            await message.answer("Отправь имя проекта:")

        case FlowAction.ASK_DIR_CHOICE:
            await state.set_state(StartFlow.awaiting_dir_choice)
            await state.update_data(project=result.project, path=result.path)
            await message.answer(
                f"Директория `{result.path}` не найдена.\n\nЧто делать?",
                reply_markup=dir_not_found_keyboard(),
            )

        case FlowAction.LAUNCH:
            await state.clear()
            # trigger launch...

        case FlowAction.ERROR:
            await message.answer(result.error)
```

### Тестирование

```python
# tests/test_start_flow_service.py
import pytest
from unittest.mock import Mock

from codogram.services.start_flow import StartFlowService, FlowAction

def test_start_with_valid_project_name():
    mock_pm = Mock()
    mock_pm.get_or_create.return_value = Mock(cwd=None)
    service = StartFlowService(mock_pm, Mock())

    result = service.handle_start(123, ["my-project"])

    assert result.action == FlowAction.ASK_DIR_CHOICE
    assert result.project == "my-project"

def test_start_with_invalid_project_name():
    service = StartFlowService(Mock(), Mock())

    result = service.handle_start(123, ["my project"])  # space

    assert result.action == FlowAction.ERROR
    assert "буквы, цифры" in result.error

def test_start_existing_project_running():
    mock_pm = Mock()
    running_project = Mock(
        project_name="test",
        cwd="/tmp",
        tmux_session="claude-test",
        poller_task=Mock(done=lambda: False),
        watcher_task=Mock(done=lambda: False),
    )
    mock_pm.get_by_chat.return_value = running_project
    service = StartFlowService(mock_pm, Mock())

    with patch("codogram.services.start_flow.is_tmux_session_exists", return_value=True):
        result = service.handle_start(123, [])

    assert result.action == FlowAction.SHOW_STATUS

def test_start_no_project_asks_name():
    mock_pm = Mock()
    mock_pm.get_by_chat.return_value = None
    service = StartFlowService(mock_pm, Mock())

    result = service.handle_start(123, [], chat_title=None)

    assert result.action == FlowAction.ASK_PROJECT_NAME
```

### Чеклист

- [ ] StartFlowService создан с методами для каждого шага
- [ ] FlowResult dataclass описывает все возможные outcomes
- [ ] aiogram FSM интегрирован
- [ ] Handlers используют service + FSM
- [ ] _start_state dict удалён
- [ ] Unit тесты на service (без Telegram)
- [ ] E2E: полный /start flow работает

### Definition of Done

- FSM логика в service, чистая и тестируемая
- Handlers тонкие — только map result → response
- Легко добавить новый шаг в flow

---

## Фаза 8: Вынести handlers/start.py

**Цель:** Собрать все start-related handlers в один файл

### Шаги

#### 8.1 handlers/start.py

```python
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..domain.states import StartFlow
from ..services.start_flow import StartFlowService, FlowResult, FlowAction
from ..services.launch import LaunchService
from ..keyboards.start_flow import (
    dir_not_found_keyboard,
    git_setup_keyboard,
    git_visibility_keyboard,
)

router = Router()

# ===== Commands =====

@router.message(Command("start"))
async def cmd_start(
    message: Message,
    state: FSMContext,
    start_flow: StartFlowService,
):
    args = message.text.split()[1:]
    result = start_flow.handle_start(
        chat_id=message.chat.id,
        args=args,
        chat_title=message.chat.title,
    )
    await _handle_result(message, state, result)

# ===== FSM States =====

@router.message(StartFlow.awaiting_project_name)
async def on_project_name(
    message: Message,
    state: FSMContext,
    start_flow: StartFlowService,
):
    result = start_flow.handle_project_name(message.chat.id, message.text.strip())
    await _handle_result(message, state, result)

@router.message(StartFlow.awaiting_custom_path)
async def on_custom_path(
    message: Message,
    state: FSMContext,
    start_flow: StartFlowService,
):
    data = await state.get_data()
    result = start_flow.handle_custom_path(
        message.chat.id, data["project"], message.text.strip()
    )
    await _handle_result(message, state, result)

@router.message(StartFlow.awaiting_clone_url)
async def on_clone_url(
    message: Message,
    state: FSMContext,
    start_flow: StartFlowService,
):
    data = await state.get_data()
    result = start_flow.handle_clone_url(
        message.chat.id, data["project"], data["path"], message.text.strip()
    )
    await _handle_result(message, state, result)

# ===== Callbacks =====

@router.callback_query(F.data == "start:create_dir")
async def on_create_dir(
    callback: CallbackQuery,
    state: FSMContext,
    start_flow: StartFlowService,
):
    data = await state.get_data()
    result = start_flow.handle_create_dir(data["project"], data["path"])
    await _handle_callback_result(callback, state, result)

@router.callback_query(F.data == "start:custom_path")
async def on_custom_path_btn(callback: CallbackQuery, state: FSMContext):
    await state.set_state(StartFlow.awaiting_custom_path)
    await callback.message.edit_text("Отправь путь к директории:")
    await callback.answer()

@router.callback_query(F.data == "start:git_init")
async def on_git_init(
    callback: CallbackQuery,
    state: FSMContext,
    start_flow: StartFlowService,
):
    data = await state.get_data()
    result = start_flow.handle_git_init(data["project"], data["path"])
    await _handle_callback_result(callback, state, result)

@router.callback_query(F.data == "start:git_gh")
async def on_git_gh(callback: CallbackQuery, state: FSMContext):
    await state.set_state(StartFlow.awaiting_gh_visibility)
    await callback.message.edit_text(
        "Видимость репозитория?",
        reply_markup=git_visibility_keyboard(),
    )
    await callback.answer()

@router.callback_query(F.data.in_({"start:gh_private", "start:gh_public"}))
async def on_gh_visibility(
    callback: CallbackQuery,
    state: FSMContext,
    start_flow: StartFlowService,
):
    data = await state.get_data()
    private = callback.data == "start:gh_private"
    result = start_flow.handle_gh_create(data["project"], data["path"], private)
    await _handle_callback_result(callback, state, result)

@router.callback_query(F.data == "start:git_clone")
async def on_git_clone(callback: CallbackQuery, state: FSMContext):
    await state.set_state(StartFlow.awaiting_clone_url)
    await callback.message.edit_text("Отправь ссылку на репозиторий:")
    await callback.answer()

@router.callback_query(F.data == "start:no_git")
async def on_no_git(
    callback: CallbackQuery,
    state: FSMContext,
    start_flow: StartFlowService,
):
    data = await state.get_data()
    result = start_flow.handle_no_git(data["project"], data["path"])
    await _handle_callback_result(callback, state, result)

@router.callback_query(F.data == "start:launch_claude")
async def on_launch_claude(
    callback: CallbackQuery,
    state: FSMContext,
    launch_service: LaunchService,
):
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_text("Запускаю Claude...")
    # Launch...
    await callback.answer()

@router.callback_query(F.data == "start:cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()

@router.callback_query(F.data.startswith("select_tmux:"))
async def on_tmux_selected(
    callback: CallbackQuery,
    state: FSMContext,
    start_flow: StartFlowService,
):
    parts = callback.data.split(":", 2)
    project_name, tmux_session = parts[1], parts[2]
    result = start_flow.handle_tmux_selected(project_name, tmux_session)
    await _handle_callback_result(callback, state, result)

# ===== Result Handlers =====

async def _handle_result(message: Message, state: FSMContext, result: FlowResult):
    """Map FlowResult to Telegram response."""
    match result.action:
        case FlowAction.ASK_PROJECT_NAME:
            await state.set_state(StartFlow.awaiting_project_name)
            await message.answer("Отправь имя проекта:")
        case FlowAction.ASK_DIR_CHOICE:
            await state.set_state(StartFlow.awaiting_dir_choice)
            await state.update_data(project=result.project, path=result.path)
            await message.answer(
                f"Директория `{result.path}` не найдена.\n\nЧто делать?",
                reply_markup=dir_not_found_keyboard(),
                parse_mode="Markdown",
            )
        case FlowAction.ERROR:
            await message.answer(result.error)
        # ... other cases

async def _handle_callback_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: FlowResult,
):
    """Map FlowResult to Telegram callback response."""
    await callback.answer()
    # Similar to _handle_result but edit message
```

#### 8.2 handlers/__init__.py

```python
from aiogram import Dispatcher
from . import permissions, start

def register_handlers(dp: Dispatcher):
    dp.include_router(permissions.router)
    dp.include_router(start.router)
```

### Чеклист

- [ ] handlers/start.py содержит все start-related handlers
- [ ] FSM states правильно используются
- [ ] Все callbacks работают
- [ ] bot.py уменьшился на ~350 строк
- [ ] E2E: полный /start flow работает

### Definition of Done

- Все start handlers в одном месте
- Чистое разделение: handler → service → response

---

## Фаза 9: Вынести handlers для thread и session управления

> **Обновлено 2025-12-30:** Разделено на 9a (threads) и 9b (sessions). Команды переименованы.

**Цель:** Handlers для управления threads и sessions

### Шаги

#### 9a.1 handlers/threads.py (NEW)

```python
"""Thread management: create and delete forum topics."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager, ThreadInfo
from ..magic_names import get_random_magic_name

router = Router()

@router.message(Command("thread_create"))
async def cmd_thread_create(message: Message):
    """Create a new thread (topic) with its own Claude session."""
    # ... same logic as old session_new ...

@router.message(Command("thread_delete"))
async def cmd_thread_delete(message: Message):
    """Delete current thread and its Claude session."""
    # ... same logic as old session_close ...

@router.callback_query(F.data.startswith("thread_delete:"))
async def on_thread_delete_callback(callback: CallbackQuery):
    # ... handle confirmation ...
```

---

#### 9b.1 handlers/sessions.py

```python
"""Session management: /new, /clear, /restart, /esc, /resume."""
import asyncio
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager
from ..tmux import TmuxSession
from ..project_launcher import is_tmux_session_exists

router = Router()

# ===== Helper =====

async def _send_session_command(message: Message, command: str, status_text: str) -> bool:
    """Common logic for /new and /clear commands."""
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Project not registered. Use /start")
        return False

    thread = project.threads.get(message.message_thread_id)
    if not thread:
        await message.answer("Thread not found. Use /start")
        return False

    tmux_name = thread.get_tmux_session(project.project_name)
    if not is_tmux_session_exists(tmux_name):
        await message.answer("tmux session not found.")
        return False

    # Mark as awaiting new session
    thread.awaiting_new_session = True
    thread.start_requested_at = time.time()
    thread.last_sent_message = None
    project_manager._save()

    # Send command to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_keys(command)

    await message.answer(status_text)
    return True

# ===== /new =====

@router.message(Command("new"))
async def cmd_new(message: Message):
    """Start new Claude session in current thread."""
    await _send_session_command(message, "/new", "`[~]` Creating new session...")

# ===== /clear =====

@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Clear Claude session and start fresh."""
    await _send_session_command(message, "/clear", "`[~]` Clearing session...")

# ===== /restart =====

@router.message(Command("restart"))
async def cmd_restart(message: Message):
    """Restart Claude session - kill tmux and require /start."""
    # ... get thread, show confirmation keyboard ...

@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery):
    # ... stop tasks, kill tmux, clear state ...

@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Cancelled.")
    await callback.answer()

# ===== /esc =====

@router.message(Command("esc"))
async def cmd_esc(message: Message):
    """Send Escape to current thread's tmux."""
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        return

    thread = project.threads.get(message.message_thread_id)
    if not thread:
        return

    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd or "/tmp")
    tmux.send_key("Escape")

# ===== /resume =====

@router.message(Command("resume"))
async def cmd_resume(message: Message):
    """Not supported in multi-session mode."""
    await message.answer(
        "`[!]` /resume not supported.\n"
        "Use /start to connect or /thread_create for new thread.",
        parse_mode="Markdown"
    )
```

#### 9.2 handlers/public.py

```python
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()

@router.message(Command("my_chat_id"))
async def cmd_my_chat_id(message: Message):
    await message.answer(
        f"User ID: `{message.from_user.id}`\n"
        f"Chat ID: `{message.chat.id}`",
        parse_mode="Markdown",
    )
```

#### 9c handlers/__init__.py (обновлённый)

```python
from aiogram import Dispatcher, Router
from . import permissions, start, threads, sessions, public
from ..middleware.admin import AdminMiddleware

def register_handlers(dp: Dispatcher):
    # Public handlers (no admin check)
    dp.include_router(public.router)

    # Admin handlers
    admin_router = Router()
    admin_router.message.middleware(AdminMiddleware())
    admin_router.callback_query.middleware(AdminMiddleware())

    admin_router.include_router(start.router)
    admin_router.include_router(threads.router)     # /thread_create, /thread_delete
    admin_router.include_router(sessions.router)    # /new, /clear, /restart, /esc
    admin_router.include_router(permissions.router)

    dp.include_router(admin_router)
```

### Чеклист (актуализирован 2025-12-30)

**9a handlers/threads.py:**
- [ ] `/thread_create` — создание топика + Claude
- [ ] `/thread_delete` — удаление топика + tmux
- [ ] Confirmation callbacks

**9b handlers/sessions.py:**
- [ ] `/new` — новая сессия Claude
- [ ] `/clear` — очистка сессии
- [ ] `/restart` — перезапуск (kill tmux)
- [ ] `/esc` — отправка Escape
- [ ] `/resume` — сообщение "not supported"

**Общее:**
- [ ] handlers/public.py для /my_chat_id
- [ ] AdminMiddleware правильно применяется
- [ ] bot.py уменьшился на ~300 строк
- [ ] E2E: все команды работают

### Definition of Done

- Thread handlers в handlers/threads.py
- Session handlers в handlers/sessions.py
- Public handlers без admin check
- В bot.py остаётся только on_message()
