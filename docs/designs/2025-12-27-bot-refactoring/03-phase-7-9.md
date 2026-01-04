# Фазы 7-9: FSM, Start, Sessions

> **Статус:** Актуализировано 2025-01-03 после code review.
>
> **Изменения:**
> - Phase 7 разбит на 7a/7b/7c по результатам ревью
> - Добавлены недостающие методы сервиса
> - Добавлена валидация длины имени проекта (>35)
> - Документирована интеграция с launch_with_animation
> - Расширено покрытие тестами

---

## Фаза 7a: StartFlowService (non-topic flow)

**Цель:** Создать service для /start flow БЕЗ topic/thread логики. bot.py не трогаем.

**Scope:** Только main chat flow + git setup. Topics будут в 7b.

### Анализ текущего flow (bot.py)

```
_start_state dict хранит:
{
    chat_id: {
        "state": "awaiting_project_name" | "awaiting_dir_choice" | ...,
        "project": str,
        "path": str,
        "tmux_name": str,      # для restart
        "thread_id": int,      # для thread flow (7b)
        "name": str,           # для thread_create_pending (7b)
    }
}

Переходы (main chat only):
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

#### 7a.1 domain/validators.py — добавить sanitize_project_name

```python
# Добавить в существующий domain/validators.py

import re

MAX_PROJECT_NAME_LENGTH = 35

def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid."""
    if not name:
        return False
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))

def sanitize_project_name(title: str) -> str | None:
    """Convert chat title to valid project name."""
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', title)
    sanitized = re.sub(r'-+', '-', sanitized).strip('-')
    if sanitized and len(sanitized) <= MAX_PROJECT_NAME_LENGTH:
        return sanitized
    return None
```

#### 7a.2 domain/states.py — FSM states

```python
from aiogram.fsm.state import State, StatesGroup

class StartFlow(StatesGroup):
    """FSM states for /start flow."""
    awaiting_project_name = State()
    awaiting_dir_choice = State()
    awaiting_git_choice = State()
    awaiting_gh_visibility = State()
    awaiting_clone_url = State()
    awaiting_custom_path = State()
    awaiting_launch_confirm = State()

class RestartFlow(StatesGroup):
    """FSM states for /restart flow (Phase 7c)."""
    awaiting_confirm = State()
```

#### 7a.3 services/start_flow.py — полный service

```python
from dataclasses import dataclass
from pathlib import Path
from enum import Enum
from typing import TYPE_CHECKING

from ..domain.validators import is_valid_project_name, sanitize_project_name, MAX_PROJECT_NAME_LENGTH

if TYPE_CHECKING:
    from ..session_manager import ProjectManager, ProjectState
    from ..services.launch import LaunchService

class FlowAction(Enum):
    """All possible outcomes of a flow step."""
    # Questions
    ASK_PROJECT_NAME = "ask_project_name"
    ASK_DIR_CHOICE = "ask_dir_choice"
    ASK_GIT_CHOICE = "ask_git_choice"
    ASK_GH_VISIBILITY = "ask_gh_visibility"
    ASK_CLONE_URL = "ask_clone_url"
    ASK_CUSTOM_PATH = "ask_custom_path"
    ASK_LAUNCH_CONFIRM = "ask_launch_confirm"
    # Actions
    SHOW_STATUS = "show_status"
    LAUNCH = "launch"
    CONNECT = "connect"
    SELECT_TMUX = "select_tmux"
    # Errors
    ERROR = "error"

@dataclass
class FlowResult:
    """Result of a flow step."""
    action: FlowAction
    project: str | None = None
    path: str | None = None
    tmux_session: str | None = None
    tmux_list: list[str] | None = None
    message: str | None = None
    error: str | None = None

class StartFlowService:
    """Business logic for /start flow (non-topic mode)."""

    def __init__(self, project_manager: "ProjectManager", launch_service: "LaunchService"):
        self.pm = project_manager
        self.launch_service = launch_service

    # ===== Entry Points =====

    def handle_start(
        self,
        chat_id: int,
        args: list[str],
        chat_title: str | None = None,
    ) -> FlowResult:
        """Entry point for /start command (non-topic mode)."""

        # Case 1: project name provided
        if args:
            project_name = args[0]
            return self._validate_and_start(chat_id, project_name)

        # Case 2: existing project for chat
        project = self.pm.get_by_chat(chat_id)
        if project:
            if self._is_claude_running(project):
                return FlowResult(
                    action=FlowAction.SHOW_STATUS,
                    project=project.project_name,
                    path=project.cwd,
                    tmux_session=project.tmux_session,
                )
            return self._start_project_flow(chat_id, project.project_name)

        # Case 3: use chat title
        if chat_title:
            sanitized = sanitize_project_name(chat_title)
            if sanitized:
                return self._start_project_flow(chat_id, sanitized)

        # Case 4: ask for project name
        return FlowResult(action=FlowAction.ASK_PROJECT_NAME)

    def _validate_and_start(self, chat_id: int, project_name: str) -> FlowResult:
        """Validate project name and start flow."""
        if len(project_name) > MAX_PROJECT_NAME_LENGTH:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"Project name too long (max {MAX_PROJECT_NAME_LENGTH} chars)"
            )
        if not is_valid_project_name(project_name):
            return FlowResult(
                action=FlowAction.ERROR,
                error="Project name can only contain letters, digits, - and _"
            )
        return self._start_project_flow(chat_id, project_name)

    # ===== FSM State Handlers =====

    def handle_project_name(self, chat_id: int, name: str) -> FlowResult:
        """Handle user input for project name."""
        return self._validate_and_start(chat_id, name.strip())

    def handle_custom_path(self, chat_id: int, project: str, path: str) -> FlowResult:
        """Handle user input for custom path."""
        expanded = Path(path).expanduser().resolve()
        if not expanded.is_dir():
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"Directory {path} does not exist"
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = str(expanded)
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=str(expanded),
        )

    def handle_clone_url(self, chat_id: int, project: str, path: str, url: str) -> FlowResult:
        """Handle user input for git clone URL."""
        from ..project_launcher import git_clone

        expanded = Path(path).expanduser()

        # Validate URL format
        if not url.startswith(('https://', 'git@', 'ssh://')):
            return FlowResult(
                action=FlowAction.ERROR,
                error="Invalid URL. Use https:// or git@ format"
            )

        result = git_clone(str(expanded), url)
        if not result.success:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"Clone failed: {result.error}"
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = str(expanded)
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=str(expanded),
        )

    # ===== Callback Handlers =====

    def handle_create_dir(self, project: str, path: str) -> FlowResult:
        """Handle 'Create directory' button."""
        expanded = Path(path).expanduser()
        expanded.mkdir(parents=True, exist_ok=True)

        return FlowResult(
            action=FlowAction.ASK_GIT_CHOICE,
            project=project,
            path=str(expanded),
        )

    def handle_git_init(self, chat_id: int, project: str, path: str) -> FlowResult:
        """Handle 'git init' button."""
        from ..project_launcher import git_init

        expanded = Path(path).expanduser()
        result = git_init(str(expanded))
        if not result.success:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"git init failed: {result.error}"
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = str(expanded)
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=str(expanded),
        )

    def handle_gh_create(self, chat_id: int, project: str, path: str, private: bool) -> FlowResult:
        """Handle GitHub repo creation."""
        from ..project_launcher import git_init_with_github

        expanded = Path(path).expanduser()

        result = git_init_with_github(str(expanded), private=private)
        if not result.success:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"GitHub creation failed: {result.error}"
            )

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = str(expanded)
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=str(expanded),
        )

    def handle_no_git(self, chat_id: int, project: str, path: str) -> FlowResult:
        """Handle 'No git' button."""
        expanded = Path(path).expanduser()

        proj = self.pm.get_or_create(project)
        proj.chat_id = chat_id
        proj.cwd = str(expanded)
        self.pm._save()

        return FlowResult(
            action=FlowAction.LAUNCH,
            project=project,
            path=str(expanded),
        )

    def handle_tmux_selected(self, chat_id: int, project_name: str, tmux_session: str) -> FlowResult:
        """Handle tmux session selection from list."""
        proj = self.pm.get_or_create(project_name)
        proj.chat_id = chat_id
        proj.tmux_session = tmux_session
        self.pm._save()

        return FlowResult(
            action=FlowAction.CONNECT,
            project=project_name,
            tmux_session=tmux_session,
        )

    # ===== Internal Methods =====

    def _start_project_flow(self, chat_id: int, project_name: str) -> FlowResult:
        """Resolve path and decide next step."""
        from ..project_launcher import resolve_project_path

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
            self.pm._save()
            return self._connect_or_launch(project)
        else:
            return FlowResult(
                action=FlowAction.ASK_DIR_CHOICE,
                project=project_name,
                path=path,
            )

    def _connect_or_launch(self, project: "ProjectState") -> FlowResult:
        """Find tmux or offer to create."""
        from ..tmux import find_all_tmux_by_cwd, find_tmux_by_convention

        tmux_list = find_all_tmux_by_cwd(project.cwd)

        if len(tmux_list) == 0:
            tmux = find_tmux_by_convention(project.project_name)
            if tmux:
                project.tmux_session = tmux
                self.pm._save()
                return FlowResult(
                    action=FlowAction.CONNECT,
                    project=project.project_name,
                    tmux_session=tmux,
                )
            else:
                return FlowResult(
                    action=FlowAction.ASK_LAUNCH_CONFIRM,
                    project=project.project_name,
                    path=project.cwd,
                )
        elif len(tmux_list) == 1:
            project.tmux_session = tmux_list[0]
            self.pm._save()
            return FlowResult(
                action=FlowAction.CONNECT,
                project=project.project_name,
                tmux_session=tmux_list[0],
            )
        else:
            return FlowResult(
                action=FlowAction.SELECT_TMUX,
                project=project.project_name,
                path=project.cwd,
                tmux_list=tmux_list,
            )

    def _is_claude_running(self, project: "ProjectState") -> bool:
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
```

#### 7a.4 Интеграция с launch_with_animation

Когда handler получает `FlowAction.LAUNCH`, он вызывает `LaunchService`:

```python
# В handlers/start.py (Phase 8)
case FlowAction.LAUNCH:
    await state.clear()
    await launch_service.launch_with_animation(
        bot=bot,
        chat_id=message.chat.id,
        project=result.project,
        path=result.path,
        telegram_queue=telegram_queue,
        start_poller=start_poller,
        start_watcher=start_watcher,
    )
```

`LaunchService` уже существует в `launch_animation.py` — используем его как есть.

### Тестирование (расширенное)

```python
# tests/test_start_flow_service.py
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from codogram.services.start_flow import StartFlowService, FlowAction

class TestHandleStart:
    def test_valid_project_name_no_dir(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None)
        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.resolve_project_path") as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/test", exists=False)
            result = service.handle_start(123, ["my-project"])

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "my-project"

    def test_invalid_project_name_with_space(self):
        service = StartFlowService(Mock(), Mock())
        result = service.handle_start(123, ["my project"])
        assert result.action == FlowAction.ERROR
        assert "letters, digits" in result.error

    def test_project_name_too_long(self):
        service = StartFlowService(Mock(), Mock())
        result = service.handle_start(123, ["a" * 40])
        assert result.action == FlowAction.ERROR
        assert "too long" in result.error

    def test_existing_project_running(self):
        mock_pm = Mock()
        running_project = Mock(
            project_name="test",
            cwd="/tmp",
            tmux_session="claude-test",
            poller_task=Mock(done=Mock(return_value=False)),
            watcher_task=Mock(done=Mock(return_value=False)),
        )
        mock_pm.get_by_chat.return_value = running_project
        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.is_tmux_session_exists", return_value=True):
            result = service.handle_start(123, [])

        assert result.action == FlowAction.SHOW_STATUS

    def test_no_project_asks_name(self):
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None
        service = StartFlowService(mock_pm, Mock())

        result = service.handle_start(123, [], chat_title=None)

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_uses_chat_title_if_valid(self):
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None
        mock_pm.get_or_create.return_value = Mock(cwd=None)
        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.resolve_project_path") as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/my-chat", exists=False)
            result = service.handle_start(123, [], chat_title="My Chat!")

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "My-Chat"

class TestConnectOrLaunch:
    def test_no_tmux_asks_launch(self):
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp", tmux_session=None)
        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.find_all_tmux_by_cwd", return_value=[]):
            with patch("codogram.services.start_flow.find_tmux_by_convention", return_value=None):
                result = service._connect_or_launch(project)

        assert result.action == FlowAction.ASK_LAUNCH_CONFIRM

    def test_one_tmux_connects(self):
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp", tmux_session=None)
        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.find_all_tmux_by_cwd", return_value=["claude-test"]):
            result = service._connect_or_launch(project)

        assert result.action == FlowAction.CONNECT
        assert result.tmux_session == "claude-test"

    def test_multiple_tmux_selects(self):
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp", tmux_session=None)
        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.find_all_tmux_by_cwd", return_value=["s1", "s2"]):
            result = service._connect_or_launch(project)

        assert result.action == FlowAction.SELECT_TMUX
        assert result.tmux_list == ["s1", "s2"]

class TestGitSetup:
    def test_create_dir(self, tmp_path):
        service = StartFlowService(Mock(), Mock())
        new_dir = tmp_path / "new_project"

        result = service.handle_create_dir("test", str(new_dir))

        assert result.action == FlowAction.ASK_GIT_CHOICE
        assert new_dir.exists()

    def test_clone_invalid_url(self):
        service = StartFlowService(Mock(), Mock())
        result = service.handle_clone_url(123, "test", "/tmp", "not-a-url")
        assert result.action == FlowAction.ERROR
        assert "Invalid URL" in result.error

    def test_custom_path_not_exists(self):
        service = StartFlowService(Mock(), Mock())
        result = service.handle_custom_path(123, "test", "/nonexistent/path")
        assert result.action == FlowAction.ERROR
        assert "does not exist" in result.error
```

### Чеклист Phase 7a

- [ ] `domain/validators.py` — добавлен `sanitize_project_name`, `MAX_PROJECT_NAME_LENGTH`
- [ ] `domain/states.py` — `StartFlow` StatesGroup
- [ ] `services/start_flow.py` — `StartFlowService` со всеми методами:
  - [ ] `handle_start()`
  - [ ] `handle_project_name()`
  - [ ] `handle_custom_path()`
  - [ ] `handle_clone_url()`
  - [ ] `handle_create_dir()`
  - [ ] `handle_git_init()`
  - [ ] `handle_gh_create()`
  - [ ] `handle_no_git()`
  - [ ] `handle_tmux_selected()`
- [ ] Unit тесты (15+ test cases)
- [ ] Imports работают: `python -c "from codogram.services.start_flow import StartFlowService"`

### Definition of Done (7a)

- Service создан и протестирован изолированно
- bot.py НЕ трогаем — service готов к использованию в Phase 8
- Валидация длины имени проекта добавлена

---

## Фаза 7b: Thread/Topic Support

**Цель:** Добавить поддержку topics в `StartFlowService`

**Scope:** Расширить `handle_start()` для работы с `thread_id`

### Текущее поведение (bot.py:269-301)

```python
# В cmd_start:
thread_id = message.message_thread_id
if thread_id is not None:
    # Topic mode
    thread = project.threads.get(thread_id)
    if thread and thread.name == "pending":
        # Upgrade pending thread
        ...
    elif thread_id not in project.threads:
        # Register unknown topic
        ...
    else:
        # Start in existing thread
        _start_thread_flow(...)
```

### Изменения в StartFlowService

```python
def handle_start(
    self,
    chat_id: int,
    args: list[str],
    chat_title: str | None = None,
    thread_id: int | None = None,  # NEW
) -> FlowResult:
    """Entry point for /start command."""

    # Topic mode
    if thread_id is not None:
        return self._handle_topic_start(chat_id, thread_id, args)

    # ... existing non-topic logic
```

### Новые FlowActions

```python
class FlowAction(Enum):
    # ... existing ...
    # Thread-specific
    UPGRADE_PENDING_THREAD = "upgrade_pending_thread"
    REGISTER_UNKNOWN_TOPIC = "register_unknown_topic"
    START_THREAD_FLOW = "start_thread_flow"
```

### Чеклист Phase 7b

- [ ] `handle_start()` принимает `thread_id`
- [ ] `_handle_topic_start()` метод
- [ ] FlowActions для thread scenarios
- [ ] Тесты для topic mode

---

## Фаза 7c: Restart Confirmation Flow

**Цель:** Добавить FSM для `/restart` confirmation

**Scope:** `RestartFlow` FSM + handler

### Текущее поведение

```python
_start_state[chat_id] = {
    "state": "restart_confirm",
    "tmux_name": tmux_session,
    "project": project_name,
}
```

### RestartFlowService

```python
class RestartFlowService:
    def handle_restart(self, chat_id: int, project: str, tmux: str) -> FlowResult:
        """Show restart confirmation."""
        return FlowResult(
            action=FlowAction.ASK_RESTART_CONFIRM,
            project=project,
            tmux_session=tmux,
        )

    def handle_confirm(self, project: str, tmux: str) -> FlowResult:
        """Execute restart."""
        # Kill tmux, clear project state
        return FlowResult(action=FlowAction.RESTART_DONE)

    def handle_cancel(self) -> FlowResult:
        return FlowResult(action=FlowAction.CANCELLED)
```

### Чеклист Phase 7c

- [ ] `RestartFlow` в `domain/states.py`
- [ ] `RestartFlowService` или методы в `StartFlowService`
- [ ] Тесты для restart flow

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

## Фаза 9: Вынести остальные handlers

> **Актуализировано 2025-01-03:** После merge с main добавились /settings, /auto_accept, /help.
> Разбито на 9a-9d. handlers/public.py удалён (AdminMiddleware на dp защищает всё).

**Цель:** Вынести все оставшиеся handlers из bot.py

### 9a handlers/threads.py (~100 LOC)

```python
"""Thread management: create and delete forum topics."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

router = Router(name="threads")

@router.message(Command("thread_create"))
async def cmd_thread_create(message: Message):
    """Create a new thread (topic) with its own Claude session."""
    ...

@router.message(Command("thread_delete"))
async def cmd_thread_delete(message: Message):
    """Delete current thread and its Claude session."""
    ...

@router.callback_query(F.data.startswith("thread_delete:"))
async def on_thread_delete_confirm(callback: CallbackQuery):
    ...

@router.callback_query(F.data == "thread_create_confirm")
async def on_thread_create_confirm(callback: CallbackQuery):
    ...
```

---

### 9b handlers/branches.py (~400 LOC) — NEW

```python
"""Branch management: git worktrees + threads."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

router = Router(name="branches")

# ===== /branch_create =====

@router.message(Command("branch_create"))
async def cmd_branch_create(message: Message):
    """Create isolated git worktree + thread."""
    ...

@router.callback_query(F.data.startswith("bc_base:"))
async def on_branch_base_selected(callback: CallbackQuery):
    ...

@router.callback_query(F.data.startswith("bc_create:"))
async def on_branch_create_confirm(callback: CallbackQuery):
    ...

@router.callback_query(F.data.startswith("bc_commit:"))
async def on_branch_commit_confirm(callback: CallbackQuery):
    ...

@router.callback_query(F.data == "branch_create_redirect")
async def on_branch_redirect(callback: CallbackQuery):
    ...

# ===== /branch_finish =====

@router.message(Command("branch_finish"))
async def cmd_branch_finish(message: Message):
    """Merge branch and cleanup worktree."""
    ...

@router.callback_query(F.data.startswith("bf_merge:"))
async def on_branch_merge_selected(callback: CallbackQuery):
    ...

@router.callback_query(F.data.startswith("bf_do_merge:"))
async def on_branch_do_merge(callback: CallbackQuery):
    ...

@router.callback_query(F.data.startswith("bf_delete:"))
async def on_branch_delete_selected(callback: CallbackQuery):
    ...

@router.callback_query(F.data.startswith("bf_do_delete:"))
async def on_branch_do_delete(callback: CallbackQuery):
    ...
```

---

### 9c handlers/sessions.py (~150 LOC)

```python
"""Session management: /new, /clear, /restart, /esc, /resume."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

router = Router(name="sessions")

async def _send_session_command(message: Message, command: str, status_text: str) -> bool:
    """Common logic for /new and /clear commands."""
    ...

@router.message(Command("new"))
async def cmd_new(message: Message):
    """Start new Claude session in current thread."""
    ...

@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Clear Claude session and start fresh."""
    ...

@router.message(Command("restart"))
async def cmd_restart(message: Message):
    """Restart Claude session - kill tmux and require /start."""
    ...

@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery):
    ...

@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery):
    ...

@router.message(Command("esc"))
async def cmd_esc(message: Message):
    """Send Escape to current thread's tmux."""
    ...

@router.message(Command("resume"))
async def cmd_resume(message: Message):
    """Not supported - show message."""
    ...
```

---

### 9d handlers/settings.py (~100 LOC) — NEW

> Новые команды из auto-accept + переименованный /get_debug_ids

```python
"""Settings and info commands."""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router(name="settings")

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Show current settings (auto-accept status)."""
    ...

@router.message(Command("auto_accept"))
async def cmd_auto_accept(message: Message):
    """Toggle auto-accept or reset all."""
    ...

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show available commands."""
    ...

@router.message(Command("get_debug_ids"))
async def cmd_get_debug_ids(message: Message):
    """Show debug IDs (user, chat, thread)."""
    ...
```

---

### 9e handlers/__init__.py (финальный)

```python
"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions, start, threads, branches, sessions, settings, messages

def register_handlers(dp: Dispatcher):
    """Register all handler routers.

    Note: All routers are protected by AdminMiddleware on dp level.
    No need to add middleware to individual routers.
    """
    dp.include_router(permissions.router)  # ✅ DONE
    dp.include_router(start.router)
    dp.include_router(threads.router)
    dp.include_router(branches.router)
    dp.include_router(sessions.router)
    dp.include_router(settings.router)
    dp.include_router(messages.router)     # Last - catch-all
```

---

### Чеклист (актуализирован 2025-01-03)

**9a handlers/threads.py:**
- [ ] `/thread_create` + confirm callback
- [ ] `/thread_delete` + confirm callback

**9b handlers/branches.py:**
- [ ] `/branch_create` + bc_* callbacks
- [ ] `/branch_finish` + bf_* callbacks

**9c handlers/sessions.py:**
- [ ] `/new`, `/clear` + helper
- [ ] `/restart` + callbacks
- [ ] `/esc`
- [ ] `/resume`

**9d handlers/settings.py:**
- [ ] `/settings` — show current settings
- [ ] `/auto_accept` — toggle or reset all
- [ ] `/help` — show commands
- [ ] `/get_debug_ids` — debug info

**9e handlers/__init__.py:**
- [ ] register_handlers imports all routers
- [ ] Correct order (messages.router last)

### Definition of Done

- Thread handlers в handlers/threads.py
- Branch handlers в handlers/branches.py
- Session handlers в handlers/sessions.py
- Settings handlers в handlers/settings.py
- В bot.py остаётся только on_message() (→ Phase 10)
