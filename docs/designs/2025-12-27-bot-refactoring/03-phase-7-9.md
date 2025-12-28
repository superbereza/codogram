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

## Фаза 9: Вынести handlers/sessions.py

**Цель:** Handlers для управления сессиями

### Шаги

#### 9.1 handlers/sessions.py

```python
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from ..session_manager import project_manager, ThreadInfo
from ..adapters.tmux import TmuxAdapter
from ..project_launcher import is_tmux_session_exists

router = Router()

# ===== /session_new =====

@router.message(Command("session_new"))
async def cmd_session_new(message: Message):
    """Create new thread with Claude session."""
    chat_id = message.chat.id
    project = project_manager.get_by_chat(chat_id)

    if not project:
        await message.answer("Проект не найден. Сначала /start")
        return

    chat = await message.bot.get_chat(chat_id)
    if not chat.is_forum:
        await message.answer("Чат не поддерживает топики.")
        return

    # Parse name
    from ..magic_names import get_random_magic_name
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        name = args[1].strip().lower()
        if not name.replace("-", "").replace("_", "").isalnum():
            await message.answer("Имя должно содержать только буквы, цифры, - и _")
            return
    else:
        existing = {t.name for t in project.threads.values() if t.name != "pending"}
        name = get_random_magic_name(existing)

    # Check duplicate
    for thread in project.threads.values():
        if thread.name == name:
            await message.answer(f"Тред '{name}' уже существует")
            return

    # Create topic
    try:
        topic = await message.bot.create_forum_topic(chat_id, name.capitalize())
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        return

    # Create ThreadInfo and launch
    thread = ThreadInfo(thread_id=topic.message_thread_id, name=name)
    project.threads[topic.message_thread_id] = thread
    project_manager._save()

# ===== /session_close =====

@router.message(Command("session_close"))
async def cmd_session_close(message: Message):
    """Close current thread."""
    if message.message_thread_id is None:
        await message.answer("Только в топике")
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Проект не найден")
        return

    thread = project.threads.get(message.message_thread_id)
    if not thread:
        await message.answer("Топик не связан с сессией")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data=f"session_close:{message.message_thread_id}"),
        InlineKeyboardButton(text="Отмена", callback_data="session_close:cancel"),
    ]])
    await message.answer(f"Закрыть '{thread.name}'?", reply_markup=keyboard)

@router.callback_query(F.data.startswith("session_close:"))
async def on_session_close(callback: CallbackQuery):
    data = callback.data.split(":")[1]

    if data == "cancel":
        await callback.message.edit_text("Отменено")
        await callback.answer()
        return

    thread_id = int(data)
    project = project_manager.get_by_chat(callback.message.chat.id)
    thread = project.threads.get(thread_id)

    # Stop tasks
    for task in [thread.watcher_task, thread.poller_task, thread.binding_task]:
        if task:
            task.cancel()

    # Kill tmux
    import subprocess
    tmux_name = thread.get_tmux_session(project.project_name)
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Delete topic
    try:
        await callback.bot.delete_forum_topic(callback.message.chat.id, thread_id)
    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")
        await callback.answer()
        return

    del project.threads[thread_id]
    project_manager._save()
    await callback.answer("Закрыто")

# ===== /restart_session =====

@router.message(Command("restart_session"))
async def cmd_restart_session(message: Message):
    project = project_manager.get_by_chat(message.chat.id)
    if not project or not project.tmux_session:
        await message.answer("Нет активной сессии")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data="restart:confirm"),
        InlineKeyboardButton(text="Отмена", callback_data="restart:cancel"),
    ]])
    await message.answer(
        f"Перезапустить `{project.tmux_session}`?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery):
    project = project_manager.get_by_chat(callback.message.chat.id)

    # Stop tasks
    for task in [project.poller_task, project.watcher_task]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # Kill tmux
    if project.tmux_session and is_tmux_session_exists(project.tmux_session):
        import subprocess
        subprocess.run(
            ["tmux", "kill-session", "-t", project.tmux_session],
            capture_output=True,
        )

    # Clear state
    project.session_id = None
    project.jsonl_path = None
    project.tmux_session = None
    project.poller_task = None
    project.watcher_task = None
    project_manager._save()

    await callback.message.edit_text("Остановлено. /start для запуска.")
    await callback.answer()

@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Отменено.")
    await callback.answer()

# ===== /esc =====

@router.message(Command("esc"))
async def cmd_esc(message: Message):
    project = project_manager.get_by_chat(message.chat.id)
    if project and project.tmux_session:
        tmux = TmuxAdapter(project.tmux_session, project.cwd or "/tmp")
        tmux.send_key("Escape")
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

#### 9.3 handlers/__init__.py (обновлённый)

```python
from aiogram import Dispatcher, Router
from . import permissions, start, sessions, public
from ..middleware.admin import AdminMiddleware

def register_handlers(dp: Dispatcher):
    # Public handlers (no admin check)
    dp.include_router(public.router)

    # Admin handlers
    admin_router = Router()
    admin_router.message.middleware(AdminMiddleware())
    admin_router.callback_query.middleware(AdminMiddleware())

    admin_router.include_router(permissions.router)
    admin_router.include_router(start.router)
    admin_router.include_router(sessions.router)

    dp.include_router(admin_router)
```

### Чеклист

- [ ] handlers/sessions.py содержит все session commands
- [ ] handlers/public.py для /my_chat_id
- [ ] AdminMiddleware правильно применяется
- [ ] bot.py уменьшился ещё на ~200 строк
- [ ] E2E: /session_new, /session_close, /restart_session работают

### Definition of Done

- Все session handlers вынесены
- Public vs Admin handlers разделены
- В bot.py остаётся только on_message()
