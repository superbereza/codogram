# Phase 7a: StartFlowService Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create `StartFlowService` with all methods for non-topic /start flow, without modifying bot.py

**Architecture:** Service layer pattern. `StartFlowService` contains pure business logic that returns `FlowResult` objects. Handlers (Phase 8) will map these results to Telegram responses. Service is testable without aiogram/Telegram dependencies.

**Tech Stack:** Python 3.11+, pytest, dataclasses, enum

---

## Task 1: Add MAX_PROJECT_NAME_LENGTH and sanitize_project_name to validators

**Files:**
- Modify: `src/codogram/domain/validators.py`
- Test: `tests/test_validators.py`

**Step 1: Write the failing tests**

Add to `tests/test_validators.py`:

```python
from codogram.domain.validators import (
    is_valid_project_name,
    sanitize_project_name,
    MAX_PROJECT_NAME_LENGTH,
)


class TestMaxProjectNameLength:
    def test_constant_is_35(self):
        assert MAX_PROJECT_NAME_LENGTH == 35

    def test_valid_name_at_max_length(self):
        name = "a" * 35
        assert is_valid_project_name(name) is True

    def test_invalid_name_over_max_length(self):
        name = "a" * 36
        assert is_valid_project_name(name) is False


class TestSanitizeProjectName:
    def test_simple_title(self):
        assert sanitize_project_name("MyProject") == "MyProject"

    def test_title_with_spaces(self):
        assert sanitize_project_name("My Project") == "My-Project"

    def test_title_with_special_chars(self):
        assert sanitize_project_name("My Project!@#") == "My-Project"

    def test_title_with_multiple_spaces(self):
        assert sanitize_project_name("My   Project") == "My-Project"

    def test_cyrillic_title(self):
        # Cyrillic gets replaced with dashes, then stripped
        result = sanitize_project_name("Мой проект")
        assert result is None or result == ""

    def test_empty_after_sanitize(self):
        assert sanitize_project_name("!!!") is None

    def test_too_long_gets_none(self):
        long_title = "a" * 50
        assert sanitize_project_name(long_title) is None

    def test_preserves_valid_chars(self):
        assert sanitize_project_name("my-project_123") == "my-project_123"
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_validators.py -v
```

Expected: FAIL with `ImportError: cannot import name 'sanitize_project_name'`

**Step 3: Implement in validators.py**

Replace content of `src/codogram/domain/validators.py`:

```python
"""Domain validators for project names and other inputs."""
import re

MAX_PROJECT_NAME_LENGTH = 35


def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid.

    Valid names:
    - Only letters, digits, dash, underscore
    - Max 35 characters
    - Not empty
    """
    if not name:
        return False
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))


def sanitize_project_name(title: str) -> str | None:
    """Convert chat title to valid project name.

    - Replaces invalid chars with dashes
    - Collapses multiple dashes
    - Strips leading/trailing dashes
    - Returns None if result is empty or too long
    """
    if not title:
        return None

    # Replace invalid chars with dash
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', title)
    # Collapse multiple dashes
    sanitized = re.sub(r'-+', '-', sanitized)
    # Strip leading/trailing dashes
    sanitized = sanitized.strip('-')

    if not sanitized:
        return None
    if len(sanitized) > MAX_PROJECT_NAME_LENGTH:
        return None

    return sanitized
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_validators.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/domain/validators.py tests/test_validators.py
git commit -m "feat(validators): add MAX_PROJECT_NAME_LENGTH and sanitize_project_name"
```

---

## Task 2: Create FlowAction enum and FlowResult dataclass

**Files:**
- Create: `src/codogram/services/start_flow.py`
- Test: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Create `tests/test_start_flow_service.py`:

```python
"""Tests for StartFlowService."""
import pytest

from codogram.services.start_flow import FlowAction, FlowResult


class TestFlowAction:
    def test_has_ask_project_name(self):
        assert FlowAction.ASK_PROJECT_NAME.value == "ask_project_name"

    def test_has_error(self):
        assert FlowAction.ERROR.value == "error"

    def test_has_launch(self):
        assert FlowAction.LAUNCH.value == "launch"


class TestFlowResult:
    def test_default_values(self):
        result = FlowResult(action=FlowAction.ERROR)
        assert result.action == FlowAction.ERROR
        assert result.project is None
        assert result.path is None
        assert result.error is None

    def test_with_all_fields(self):
        result = FlowResult(
            action=FlowAction.ASK_DIR_CHOICE,
            project="my-project",
            path="/tmp/my-project",
            message="Choose action",
        )
        assert result.project == "my-project"
        assert result.path == "/tmp/my-project"
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestFlowAction -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'codogram.services.start_flow'`

**Step 3: Create start_flow.py with enums and dataclass**

Create `src/codogram/services/start_flow.py`:

```python
"""StartFlowService - business logic for /start flow."""
from dataclasses import dataclass
from enum import Enum


class FlowAction(Enum):
    """All possible outcomes of a flow step."""

    # Questions - need user input
    ASK_PROJECT_NAME = "ask_project_name"
    ASK_DIR_CHOICE = "ask_dir_choice"
    ASK_GIT_CHOICE = "ask_git_choice"
    ASK_GH_VISIBILITY = "ask_gh_visibility"
    ASK_CLONE_URL = "ask_clone_url"
    ASK_CUSTOM_PATH = "ask_custom_path"
    ASK_LAUNCH_CONFIRM = "ask_launch_confirm"

    # Actions - perform operation
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
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add FlowAction enum and FlowResult dataclass"
```

---

## Task 3: Create StartFlowService skeleton with handle_start (project name arg)

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write failing tests for handle_start with project name arg**

Add to `tests/test_start_flow_service.py`:

```python
from unittest.mock import Mock, patch

from codogram.services.start_flow import FlowAction, FlowResult, StartFlowService


class TestHandleStartWithProjectName:
    """Tests for handle_start when project name is provided in args."""

    def test_valid_project_name_no_existing_dir(self):
        """Valid project name, directory doesn't exist -> ASK_DIR_CHOICE."""
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/my-project", exists=False)
            result = service.handle_start(chat_id=123, args=["my-project"])

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "my-project"
        assert result.path == "/tmp/my-project"

    def test_invalid_project_name_with_space(self):
        """Project name with space -> ERROR."""
        service = StartFlowService(Mock(), Mock())

        result = service.handle_start(chat_id=123, args=["my project"])

        assert result.action == FlowAction.ERROR
        assert "letters, digits" in result.error.lower() or "only contain" in result.error.lower()

    def test_project_name_too_long(self):
        """Project name > 35 chars -> ERROR."""
        service = StartFlowService(Mock(), Mock())

        result = service.handle_start(chat_id=123, args=["a" * 40])

        assert result.action == FlowAction.ERROR
        assert "too long" in result.error.lower()
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleStartWithProjectName -v
```

Expected: FAIL with `AttributeError: module has no attribute 'StartFlowService'`

**Step 3: Implement StartFlowService with handle_start (partial)**

Add to `src/codogram/services/start_flow.py`:

```python
from typing import TYPE_CHECKING

from ..domain.validators import (
    is_valid_project_name,
    sanitize_project_name,
    MAX_PROJECT_NAME_LENGTH,
)
from ..project_launcher import resolve_project_path

if TYPE_CHECKING:
    from ..session_manager import ProjectManager


class StartFlowService:
    """Business logic for /start flow (non-topic mode)."""

    def __init__(self, project_manager: "ProjectManager", launch_service):
        self.pm = project_manager
        self.launch_service = launch_service

    def handle_start(
        self,
        chat_id: int,
        args: list[str],
        chat_title: str | None = None,
    ) -> FlowResult:
        """Entry point for /start command (non-topic mode).

        Args:
            chat_id: Telegram chat ID
            args: Command arguments (e.g., ["project-name"])
            chat_title: Chat title for auto-naming

        Returns:
            FlowResult with next action to take
        """
        # Case 1: project name provided in args
        if args:
            project_name = args[0]
            return self._validate_and_start(chat_id, project_name)

        # TODO: Other cases in next tasks
        return FlowResult(action=FlowAction.ASK_PROJECT_NAME)

    def _validate_and_start(self, chat_id: int, project_name: str) -> FlowResult:
        """Validate project name and start flow."""
        # Check length first
        if len(project_name) > MAX_PROJECT_NAME_LENGTH:
            return FlowResult(
                action=FlowAction.ERROR,
                error=f"Project name too long (max {MAX_PROJECT_NAME_LENGTH} chars)",
            )

        # Check valid characters
        if not is_valid_project_name(project_name):
            return FlowResult(
                action=FlowAction.ERROR,
                error="Project name can only contain letters, digits, - and _",
            )

        return self._start_project_flow(chat_id, project_name)

    def _start_project_flow(self, chat_id: int, project_name: str) -> FlowResult:
        """Resolve path and decide next step."""
        project = self.pm.get_or_create(project_name)
        project.chat_id = chat_id

        # Get path
        if project.cwd:
            path = project.cwd
            exists = True  # If cwd is set, assume it exists
        else:
            path_result = resolve_project_path(project_name, None)
            path = path_result.path
            exists = path_result.exists

        if exists:
            project.cwd = path
            # TODO: _connect_or_launch in next task
            return FlowResult(
                action=FlowAction.ASK_LAUNCH_CONFIRM,
                project=project_name,
                path=path,
            )
        else:
            return FlowResult(
                action=FlowAction.ASK_DIR_CHOICE,
                project=project_name,
                path=path,
            )
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleStartWithProjectName -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add StartFlowService with handle_start (project name validation)"
```

---

## Task 4: Add handle_start for existing project and chat title

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleStartNoArgs:
    """Tests for handle_start when no args provided."""

    def test_no_project_no_title_asks_name(self):
        """No project, no chat title -> ASK_PROJECT_NAME."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_start(chat_id=123, args=[], chat_title=None)

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_uses_chat_title_if_valid(self):
        """No project, valid chat title -> start flow with sanitized title."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/My-Project", exists=False)
            result = service.handle_start(
                chat_id=123, args=[], chat_title="My Project!"
            )

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "My-Project"

    def test_ignores_invalid_chat_title(self):
        """Chat title that sanitizes to empty -> ASK_PROJECT_NAME."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_start(chat_id=123, args=[], chat_title="!!!")

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_existing_project_not_running(self):
        """Existing project for chat, not running -> start flow."""
        mock_pm = Mock()
        existing = Mock(
            project_name="existing-project",
            cwd=None,
            chat_id=123,
            tmux_session=None,
        )
        mock_pm.get_by_chat.return_value = existing
        mock_pm.get_or_create.return_value = existing

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(
                path="/tmp/existing-project", exists=False
            )
            result = service.handle_start(chat_id=123, args=[])

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "existing-project"
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleStartNoArgs -v
```

Expected: FAIL (test_uses_chat_title fails - no chat title handling)

**Step 3: Implement handle_start for existing project and chat title**

Update `handle_start` in `src/codogram/services/start_flow.py`:

```python
def handle_start(
    self,
    chat_id: int,
    args: list[str],
    chat_title: str | None = None,
) -> FlowResult:
    """Entry point for /start command (non-topic mode)."""
    # Case 1: project name provided in args
    if args:
        project_name = args[0]
        return self._validate_and_start(chat_id, project_name)

    # Case 2: existing project for this chat
    project = self.pm.get_by_chat(chat_id)
    if project:
        return self._start_project_flow(chat_id, project.project_name)

    # Case 3: use chat title if valid
    if chat_title:
        sanitized = sanitize_project_name(chat_title)
        if sanitized:
            return self._start_project_flow(chat_id, sanitized)

    # Case 4: ask for project name
    return FlowResult(action=FlowAction.ASK_PROJECT_NAME)
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleStartNoArgs -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): handle existing project and chat title in handle_start"
```

---

## Task 5: Add _connect_or_launch and SHOW_STATUS for running projects

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestConnectOrLaunch:
    """Tests for _connect_or_launch method."""

    def test_no_tmux_found_asks_launch(self):
        """No tmux sessions in cwd -> ASK_LAUNCH_CONFIRM."""
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp/test", tmux_session=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.find_all_tmux_by_cwd", return_value=[]
        ):
            with patch(
                "codogram.services.start_flow.find_tmux_by_convention",
                return_value=None,
            ):
                result = service._connect_or_launch(project)

        assert result.action == FlowAction.ASK_LAUNCH_CONFIRM
        assert result.project == "test"
        assert result.path == "/tmp/test"

    def test_one_tmux_found_connects(self):
        """One tmux session in cwd -> CONNECT."""
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp/test", tmux_session=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.find_all_tmux_by_cwd",
            return_value=["claude-test"],
        ):
            result = service._connect_or_launch(project)

        assert result.action == FlowAction.CONNECT
        assert result.tmux_session == "claude-test"
        assert project.tmux_session == "claude-test"

    def test_multiple_tmux_found_selects(self):
        """Multiple tmux sessions -> SELECT_TMUX."""
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp/test", tmux_session=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.find_all_tmux_by_cwd",
            return_value=["session1", "session2"],
        ):
            result = service._connect_or_launch(project)

        assert result.action == FlowAction.SELECT_TMUX
        assert result.tmux_list == ["session1", "session2"]

    def test_finds_by_convention(self):
        """No tmux in cwd, but found by convention -> CONNECT."""
        mock_pm = Mock()
        project = Mock(project_name="myproj", cwd="/tmp/myproj", tmux_session=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.find_all_tmux_by_cwd", return_value=[]
        ):
            with patch(
                "codogram.services.start_flow.find_tmux_by_convention",
                return_value="claude-myproj",
            ):
                result = service._connect_or_launch(project)

        assert result.action == FlowAction.CONNECT
        assert result.tmux_session == "claude-myproj"


class TestShowStatus:
    """Tests for showing status of running project."""

    def test_running_project_shows_status(self):
        """Running project -> SHOW_STATUS."""
        mock_pm = Mock()
        running = Mock(
            project_name="running",
            cwd="/tmp/running",
            tmux_session="claude-running",
            poller_task=Mock(done=Mock(return_value=False)),
            watcher_task=Mock(done=Mock(return_value=False)),
        )
        mock_pm.get_by_chat.return_value = running

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.is_tmux_session_exists", return_value=True
        ):
            result = service.handle_start(chat_id=123, args=[])

        assert result.action == FlowAction.SHOW_STATUS
        assert result.project == "running"
        assert result.tmux_session == "claude-running"
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestConnectOrLaunch -v
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestShowStatus -v
```

Expected: FAIL

**Step 3: Implement _connect_or_launch and _is_claude_running**

Add to `src/codogram/services/start_flow.py` (add imports at top):

```python
from ..tmux import find_all_tmux_by_cwd, find_tmux_by_convention
from ..project_launcher import resolve_project_path, is_tmux_session_exists
```

Add methods to StartFlowService:

```python
def _connect_or_launch(self, project) -> FlowResult:
    """Find tmux or offer to create."""
    tmux_list = find_all_tmux_by_cwd(project.cwd)

    if len(tmux_list) == 0:
        # Try convention naming
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

def _is_claude_running(self, project) -> bool:
    """Check if Claude is running for project."""
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

Update `handle_start` to check if running:

```python
# Case 2: existing project for this chat
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
```

Update `_start_project_flow` to use `_connect_or_launch`:

```python
if exists:
    project.cwd = path
    self.pm._save()
    return self._connect_or_launch(project)
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestConnectOrLaunch -v
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestShowStatus -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add _connect_or_launch and SHOW_STATUS support"
```

---

## Task 6: Add handle_project_name

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleProjectName:
    """Tests for handle_project_name (FSM state handler)."""

    def test_valid_name_starts_flow(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/test", exists=False)
            result = service.handle_project_name(chat_id=123, name="my-project")

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "my-project"

    def test_invalid_name_returns_error(self):
        service = StartFlowService(Mock(), Mock())
        result = service.handle_project_name(chat_id=123, name="invalid name")

        assert result.action == FlowAction.ERROR

    def test_strips_whitespace(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/test", exists=False)
            result = service.handle_project_name(chat_id=123, name="  my-project  ")

        assert result.project == "my-project"
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleProjectName -v
```

**Step 3: Implement handle_project_name**

Add to StartFlowService:

```python
def handle_project_name(self, chat_id: int, name: str) -> FlowResult:
    """Handle user input for project name (FSM state handler)."""
    return self._validate_and_start(chat_id, name.strip())
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleProjectName -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add handle_project_name"
```

---

## Task 7: Add handle_create_dir and handle_custom_path

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleCreateDir:
    """Tests for handle_create_dir (Create directory button)."""

    def test_creates_dir_and_asks_git(self, tmp_path):
        service = StartFlowService(Mock(), Mock())
        new_dir = tmp_path / "new_project"

        result = service.handle_create_dir(project="test", path=str(new_dir))

        assert result.action == FlowAction.ASK_GIT_CHOICE
        assert result.project == "test"
        assert new_dir.exists()

    def test_works_with_existing_dir(self, tmp_path):
        service = StartFlowService(Mock(), Mock())
        existing = tmp_path / "existing"
        existing.mkdir()

        result = service.handle_create_dir(project="test", path=str(existing))

        assert result.action == FlowAction.ASK_GIT_CHOICE


class TestHandleCustomPath:
    """Tests for handle_custom_path (Custom path input)."""

    def test_valid_path_launches(self, tmp_path):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_custom_path(
            chat_id=123, project="test", path=str(tmp_path)
        )

        assert result.action == FlowAction.LAUNCH
        assert result.project == "test"
        assert result.path == str(tmp_path)

    def test_nonexistent_path_returns_error(self):
        service = StartFlowService(Mock(), Mock())
        result = service.handle_custom_path(
            chat_id=123, project="test", path="/nonexistent/path"
        )

        assert result.action == FlowAction.ERROR
        assert "not exist" in result.error.lower() or "does not exist" in result.error.lower()

    def test_expands_tilde(self, tmp_path, monkeypatch):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        # Mock Path.home() to return tmp_path
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        service = StartFlowService(mock_pm, Mock())
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = service.handle_custom_path(
            chat_id=123, project="test", path="~/test"
        )

        assert result.action == FlowAction.LAUNCH
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleCreateDir -v
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleCustomPath -v
```

**Step 3: Implement methods**

Add to StartFlowService:

```python
from pathlib import Path

def handle_create_dir(self, project: str, path: str) -> FlowResult:
    """Handle 'Create directory' button."""
    expanded = Path(path).expanduser()
    expanded.mkdir(parents=True, exist_ok=True)

    return FlowResult(
        action=FlowAction.ASK_GIT_CHOICE,
        project=project,
        path=str(expanded),
    )

def handle_custom_path(self, chat_id: int, project: str, path: str) -> FlowResult:
    """Handle user input for custom path."""
    expanded = Path(path).expanduser().resolve()

    if not expanded.is_dir():
        return FlowResult(
            action=FlowAction.ERROR,
            error=f"Directory {path} does not exist",
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
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleCreateDir -v
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleCustomPath -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add handle_create_dir and handle_custom_path"
```

---

## Task 8: Add git methods (handle_git_init, handle_no_git, handle_gh_create)

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestGitMethods:
    """Tests for git-related methods."""

    def test_handle_git_init_launches(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.git_init") as mock_git:
            mock_git.return_value = Mock(success=True)
            result = service.handle_git_init(
                chat_id=123, project="test", path="/tmp/test"
            )

        assert result.action == FlowAction.LAUNCH
        mock_git.assert_called_once_with("/tmp/test")

    def test_handle_no_git_launches(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_no_git(
            chat_id=123, project="test", path="/tmp/test"
        )

        assert result.action == FlowAction.LAUNCH
        assert result.project == "test"

    def test_handle_gh_create_private(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.git_init_with_github") as mock_gh:
            mock_gh.return_value = Mock(success=True)
            result = service.handle_gh_create(
                chat_id=123, project="test", path="/tmp/test", private=True
            )

        assert result.action == FlowAction.LAUNCH
        mock_gh.assert_called_once_with("/tmp/test", private=True)

    def test_handle_gh_create_error(self):
        mock_pm = Mock()
        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.git_init_with_github") as mock_gh:
            mock_gh.return_value = Mock(success=False, error="gh auth required")
            result = service.handle_gh_create(
                chat_id=123, project="test", path="/tmp/test", private=False
            )

        assert result.action == FlowAction.ERROR
        assert "gh auth" in result.error.lower() or "failed" in result.error.lower()
```

**Step 2: Run tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestGitMethods -v
```

**Step 3: Implement methods**

Add imports:

```python
from ..project_launcher import git_init, git_init_with_github
```

Add to StartFlowService:

```python
def handle_git_init(self, chat_id: int, project: str, path: str) -> FlowResult:
    """Handle 'git init' button."""
    result = git_init(path)

    if not result.success:
        return FlowResult(
            action=FlowAction.ERROR,
            error=f"git init failed: {result.error}",
        )

    proj = self.pm.get_or_create(project)
    proj.chat_id = chat_id
    proj.cwd = path
    self.pm._save()

    return FlowResult(
        action=FlowAction.LAUNCH,
        project=project,
        path=path,
    )

def handle_no_git(self, chat_id: int, project: str, path: str) -> FlowResult:
    """Handle 'No git' button."""
    proj = self.pm.get_or_create(project)
    proj.chat_id = chat_id
    proj.cwd = path
    self.pm._save()

    return FlowResult(
        action=FlowAction.LAUNCH,
        project=project,
        path=path,
    )

def handle_gh_create(
    self, chat_id: int, project: str, path: str, private: bool
) -> FlowResult:
    """Handle GitHub repo creation."""
    result = git_init_with_github(path, private=private)

    if not result.success:
        return FlowResult(
            action=FlowAction.ERROR,
            error=f"GitHub creation failed: {result.error}",
        )

    proj = self.pm.get_or_create(project)
    proj.chat_id = chat_id
    proj.cwd = path
    self.pm._save()

    return FlowResult(
        action=FlowAction.LAUNCH,
        project=project,
        path=path,
    )
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestGitMethods -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add handle_git_init, handle_no_git, handle_gh_create"
```

---

## Task 9: Add handle_clone_url and handle_tmux_selected

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleCloneUrl:
    """Tests for handle_clone_url."""

    def test_valid_https_url(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.git_clone") as mock_clone:
            mock_clone.return_value = Mock(success=True)
            result = service.handle_clone_url(
                chat_id=123,
                project="test",
                path="/tmp/test",
                url="https://github.com/user/repo.git",
            )

        assert result.action == FlowAction.LAUNCH
        mock_clone.assert_called_once()

    def test_valid_ssh_url(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.git_clone") as mock_clone:
            mock_clone.return_value = Mock(success=True)
            result = service.handle_clone_url(
                chat_id=123,
                project="test",
                path="/tmp/test",
                url="git@github.com:user/repo.git",
            )

        assert result.action == FlowAction.LAUNCH

    def test_invalid_url_format(self):
        service = StartFlowService(Mock(), Mock())
        result = service.handle_clone_url(
            chat_id=123,
            project="test",
            path="/tmp/test",
            url="not-a-valid-url",
        )

        assert result.action == FlowAction.ERROR
        assert "invalid" in result.error.lower() or "url" in result.error.lower()

    def test_clone_failure(self):
        service = StartFlowService(Mock(), Mock())

        with patch("codogram.services.start_flow.git_clone") as mock_clone:
            mock_clone.return_value = Mock(success=False, error="repo not found")
            result = service.handle_clone_url(
                chat_id=123,
                project="test",
                path="/tmp/test",
                url="https://github.com/user/repo.git",
            )

        assert result.action == FlowAction.ERROR


class TestHandleTmuxSelected:
    """Tests for handle_tmux_selected."""

    def test_selects_tmux_and_connects(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_tmux_selected(
            chat_id=123,
            project_name="test",
            tmux_session="session-1",
        )

        assert result.action == FlowAction.CONNECT
        assert result.tmux_session == "session-1"
        mock_pm._save.assert_called_once()
```

**Step 2: Run tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleCloneUrl -v
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleTmuxSelected -v
```

**Step 3: Implement methods**

Add import:

```python
from ..project_launcher import git_clone
```

Add to StartFlowService:

```python
def handle_clone_url(
    self, chat_id: int, project: str, path: str, url: str
) -> FlowResult:
    """Handle user input for git clone URL."""
    # Validate URL format
    if not url.startswith(("https://", "git@", "ssh://")):
        return FlowResult(
            action=FlowAction.ERROR,
            error="Invalid URL. Use https:// or git@ format",
        )

    result = git_clone(path, url)

    if not result.success:
        return FlowResult(
            action=FlowAction.ERROR,
            error=f"Clone failed: {result.error}",
        )

    proj = self.pm.get_or_create(project)
    proj.chat_id = chat_id
    proj.cwd = path
    self.pm._save()

    return FlowResult(
        action=FlowAction.LAUNCH,
        project=project,
        path=path,
    )

def handle_tmux_selected(
    self, chat_id: int, project_name: str, tmux_session: str
) -> FlowResult:
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
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleCloneUrl -v
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleTmuxSelected -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add handle_clone_url and handle_tmux_selected"
```

---

## Task 10: Final verification and cleanup

**Files:**
- All files from previous tasks

**Step 1: Run all tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py tests/test_validators.py -v
```

Expected: All tests PASS

**Step 2: Run full test suite**

```bash
PYTHONPATH=src pytest tests/ -v
```

Expected: All 159+ tests PASS

**Step 3: Verify imports work**

```bash
PYTHONPATH=src python -c "from codogram.services.start_flow import StartFlowService, FlowAction, FlowResult; print('OK')"
```

Expected: OK

**Step 4: Final commit if needed**

```bash
git status
# If any uncommitted changes:
git add -A
git commit -m "chore: cleanup Phase 7a implementation"
```

---

## Summary

**Files created/modified:**
- `src/codogram/domain/validators.py` - added `MAX_PROJECT_NAME_LENGTH`, `sanitize_project_name`
- `src/codogram/services/start_flow.py` - created `StartFlowService` with all methods
- `tests/test_validators.py` - added tests for new validators
- `tests/test_start_flow_service.py` - created comprehensive test suite

**Methods implemented in StartFlowService:**
1. `handle_start()` - entry point
2. `handle_project_name()` - FSM state handler
3. `handle_custom_path()` - custom path input
4. `handle_create_dir()` - create directory button
5. `handle_git_init()` - git init button
6. `handle_no_git()` - no git button
7. `handle_gh_create()` - GitHub create button
8. `handle_clone_url()` - clone URL input
9. `handle_tmux_selected()` - tmux selection

**Next steps:**
- Phase 7b: Add thread/topic support
- Phase 7c: Add restart flow
- Phase 8: Create handlers/start.py that uses StartFlowService
