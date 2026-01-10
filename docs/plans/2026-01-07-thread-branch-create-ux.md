# Thread/Branch Create UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show name selection prompt when `/branch` or `/thread` called without argument instead of auto-creating with random name.

**Architecture:**
- Domain types only (no state) in `domain/create_flow.py`
- Business logic + singleton in `services/create_flow.py`
- State in existing `_flow_state` with key `(chat_id, thread_id)`
- Middleware to clear state on commands
- Thin handlers that delegate to service

**Tech Stack:** aiogram, existing `_flow_state`, `sanitize_branch_name`, `get_random_magic_name`

---

### Task 1: Add CreateType enum to domain

**Files:**
- Create: `src/codogram/domain/create_flow.py`
- Test: `tests/test_create_flow_domain.py`

**Step 1: Write tests**

```python
"""Tests for create flow domain types."""
import pytest
from codogram.domain.create_flow import CreateType


def test_create_type_values():
    assert CreateType.BRANCH.value == "branch"
    assert CreateType.THREAD.value == "thread"


def test_create_type_from_string():
    assert CreateType("branch") == CreateType.BRANCH
    assert CreateType("thread") == CreateType.THREAD
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_create_flow_domain.py -v
```

**Step 3: Create domain module**

```python
"""Domain types for create flow (branch/thread)."""
from enum import Enum


class CreateType(Enum):
    """Type of entity to create."""
    BRANCH = "branch"
    THREAD = "thread"
```

**Step 4: Run test**

```bash
pytest tests/test_create_flow_domain.py -v
```

**Step 5: Commit**

```bash
git add src/codogram/domain/create_flow.py tests/test_create_flow_domain.py
git commit -m "feat(domain): add CreateType enum"
```

---

### Task 2: Update _flow_state to use (chat_id, thread_id) key

**Files:**
- Modify: `src/codogram/handlers/common.py`
- Test: `tests/test_flow_state.py`

**Step 1: Write tests**

```python
"""Tests for flow state management."""
import pytest
from codogram.handlers.common import (
    get_flow_state,
    set_flow_state,
    clear_flow_state,
    clear_flow_state_by_type,
    has_flow_state,
)


def test_set_and_get_state():
    set_flow_state(-100, 456, {"type": "test", "data": "value"})
    state = get_flow_state(-100, 456)
    assert state is not None
    assert state["type"] == "test"
    clear_flow_state(-100, 456)


def test_get_state_returns_none_when_empty():
    clear_flow_state(-100, 999)
    assert get_flow_state(-100, 999) is None


def test_different_threads_independent():
    """State in different threads should not conflict."""
    set_flow_state(-100, 1, {"type": "a"})
    set_flow_state(-100, 2, {"type": "b"})

    assert get_flow_state(-100, 1)["type"] == "a"
    assert get_flow_state(-100, 2)["type"] == "b"

    clear_flow_state(-100, 1)
    clear_flow_state(-100, 2)


def test_none_thread_id():
    """None thread_id (General topic) works correctly."""
    set_flow_state(-100, None, {"type": "general"})
    assert get_flow_state(-100, None)["type"] == "general"
    clear_flow_state(-100, None)


def test_clear_flow_state_by_type():
    """Clear only states of specific type."""
    set_flow_state(-100, 1, {"type": "awaiting_create_name"})
    set_flow_state(-100, 2, {"type": "other"})

    clear_flow_state_by_type(-100, 1, "awaiting_create_name")

    assert get_flow_state(-100, 1) is None
    assert get_flow_state(-100, 2) is not None

    clear_flow_state(-100, 2)


def test_has_flow_state():
    clear_flow_state(-100, 1)
    assert has_flow_state(-100, 1) is False

    set_flow_state(-100, 1, {"type": "test"})
    assert has_flow_state(-100, 1) is True

    clear_flow_state(-100, 1)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_flow_state.py -v
```

**Step 3: Update common.py**

Replace old `_flow_state` with new implementation:

```python
"""Common handlers and helpers used by multiple modules."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from ..telegram_queue import TelegramQueue

router = Router(name="common")

# Flow state storage with (chat_id, thread_id) key
_flow_state: dict[tuple[int, int | None], dict] = {}


def get_flow_state(chat_id: int, thread_id: int | None) -> dict | None:
    """Get flow state for chat/thread."""
    return _flow_state.get((chat_id, thread_id))


def set_flow_state(chat_id: int, thread_id: int | None, state: dict) -> None:
    """Set flow state for chat/thread."""
    _flow_state[(chat_id, thread_id)] = state


def clear_flow_state(chat_id: int, thread_id: int | None) -> None:
    """Clear flow state for chat/thread."""
    _flow_state.pop((chat_id, thread_id), None)


def clear_flow_state_by_type(chat_id: int, thread_id: int | None, state_type: str) -> None:
    """Clear flow state only if it matches the given type."""
    key = (chat_id, thread_id)
    state = _flow_state.get(key)
    if state and state.get("type") == state_type:
        _flow_state.pop(key, None)


def has_flow_state(chat_id: int, thread_id: int | None) -> bool:
    """Check if chat/thread has flow state."""
    return (chat_id, thread_id) in _flow_state


async def require_forum_group(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await telegram_queue.reply(message, "`[!]` This command requires a group with topics.")
        return False
    if not message.chat.is_forum:
        await telegram_queue.reply(message, "`[!]` Topics required. Enable in group settings -> Topics")
        return False
    return True


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle generic cancel button."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    clear_flow_state(chat_id, thread_id)
    await telegram_queue.edit(callback.message, "Cancelled.")
    await callback.answer()
```

**Step 4: Run test**

```bash
pytest tests/test_flow_state.py -v
```

**Step 5: Update existing usages of _flow_state**

Search for all usages and update to new API. Check:
- `handlers/threads.py` — `thread_create_pending` flow
- `handlers/branches.py` — any existing usage

**Step 6: Run all tests**

```bash
pytest -v
```

**Step 7: Commit**

```bash
git add src/codogram/handlers/common.py tests/test_flow_state.py
git commit -m "refactor(common): flow state with (chat_id, thread_id) key"
```

---

### Task 3: Create middleware to clear state on commands

**Files:**
- Create: `src/codogram/middleware/clear_create_state.py`
- Modify: `src/codogram/main.py`
- Test: `tests/test_clear_create_state_middleware.py`

**Step 1: Write tests**

```python
"""Tests for clear create state middleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat

from codogram.middleware.clear_create_state import ClearCreateStateMiddleware
from codogram.handlers.common import set_flow_state, get_flow_state, clear_flow_state


@pytest.fixture
def middleware():
    return ClearCreateStateMiddleware()


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.message_thread_id = 456
    msg.text = "/help"
    return msg


@pytest.mark.asyncio
async def test_clears_create_state_on_command(middleware, mock_message):
    """Command clears awaiting_create_name state."""
    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "branch"})

    handler = AsyncMock()
    await middleware(handler, mock_message, {})

    assert get_flow_state(-100123, 456) is None
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_does_not_clear_other_state_types(middleware, mock_message):
    """Command does not clear other state types."""
    set_flow_state(-100123, 456, {"type": "thread_create_pending", "name": "test"})

    handler = AsyncMock()
    await middleware(handler, mock_message, {})

    state = get_flow_state(-100123, 456)
    assert state is not None
    assert state["type"] == "thread_create_pending"

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_does_not_affect_non_commands(middleware, mock_message):
    """Non-command messages don't trigger state clearing."""
    mock_message.text = "regular message"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name"})

    handler = AsyncMock()
    await middleware(handler, mock_message, {})

    assert get_flow_state(-100123, 456) is not None

    clear_flow_state(-100123, 456)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_clear_create_state_middleware.py -v
```

**Step 3: Create middleware**

```python
"""Middleware to clear create flow state when command is received."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from ..handlers.common import clear_flow_state_by_type


class ClearCreateStateMiddleware(BaseMiddleware):
    """Clear awaiting_create_name state when any command is received.

    This prevents stale prompts: if user sends /branch, then /help,
    then types a name - it won't accidentally create a branch.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        # Only process text messages that are commands
        if event.text and event.text.startswith("/"):
            clear_flow_state_by_type(
                event.chat.id,
                event.message_thread_id,
                "awaiting_create_name",
            )

        return await handler(event, data)
```

**Step 4: Run test**

```bash
pytest tests/test_clear_create_state_middleware.py -v
```

**Step 5: Register middleware in main.py**

Find where middlewares are registered and add:

```python
from .middleware.clear_create_state import ClearCreateStateMiddleware

# In setup_dispatcher or similar:
dp.message.middleware(ClearCreateStateMiddleware())
```

**Step 6: Commit**

```bash
git add src/codogram/middleware/clear_create_state.py tests/test_clear_create_state_middleware.py src/codogram/main.py
git commit -m "feat(middleware): clear create state on commands"
```

---

### Task 4: Create service with validation

**Files:**
- Create: `src/codogram/services/create_flow.py`
- Test: `tests/test_create_flow_service.py`

**Step 1: Write tests**

```python
"""Tests for create flow service."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from codogram.services.create_flow import create_flow_service
from codogram.domain.create_flow import CreateType


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.project_name = "testproject"
    project.cwd = "/tmp/test"
    project.threads = {}
    return project


def test_should_show_prompt_no_name():
    assert create_flow_service.should_show_prompt(None) is True


def test_should_show_prompt_with_name():
    assert create_flow_service.should_show_prompt("mystic") is False


def test_should_show_prompt_empty_string():
    assert create_flow_service.should_show_prompt("") is True


def test_should_show_prompt_whitespace():
    assert create_flow_service.should_show_prompt("   ") is True


def test_get_magic_name(mock_project):
    name = create_flow_service.get_magic_name(mock_project)
    assert name is not None
    assert len(name) > 0


def test_get_magic_name_excludes_existing(mock_project):
    existing_thread = MagicMock()
    existing_thread.name = "arcane"
    mock_project.threads = {1: existing_thread}

    names = [create_flow_service.get_magic_name(mock_project) for _ in range(10)]
    assert "arcane" not in names


def test_validate_name_success(mock_project):
    name, error = create_flow_service.validate_name("my-feature", mock_project)
    assert error is None
    assert name == "my-feature"


def test_validate_name_sanitizes(mock_project):
    name, error = create_flow_service.validate_name("My Feature", mock_project)
    assert error is None
    assert name == "my-feature"


def test_validate_name_empty_after_sanitize(mock_project):
    name, error = create_flow_service.validate_name("!!!", mock_project)
    assert name is None
    assert "Invalid" in error


def test_validate_name_too_long(mock_project):
    long_name = "a" * 100
    name, error = create_flow_service.validate_name(long_name, mock_project)
    assert name is None
    assert "too long" in error


def test_validate_name_already_exists(mock_project):
    existing = MagicMock()
    existing.name = "mystic"
    mock_project.threads = {1: existing}

    name, error = create_flow_service.validate_name("mystic", mock_project)
    assert name is None
    assert "already used" in error


def test_check_branch_preconditions_no_git(mock_project):
    with patch("codogram.services.create_flow.is_git_repo", return_value=False):
        can, error, warning = create_flow_service.check_branch_preconditions(mock_project, "test")
        assert can is False
        assert "Git" in error


def test_check_branch_preconditions_uncommitted(mock_project):
    with patch("codogram.services.create_flow.is_git_repo", return_value=True), \
         patch("codogram.services.create_flow.has_uncommitted_changes", return_value=True):
        can, error, warning = create_flow_service.check_branch_preconditions(mock_project, "test")
        assert can is False
        assert error is None
        assert "Uncommitted" in warning


def test_check_branch_preconditions_success(mock_project):
    with patch("codogram.services.create_flow.is_git_repo", return_value=True), \
         patch("codogram.services.create_flow.has_uncommitted_changes", return_value=False):
        can, error, warning = create_flow_service.check_branch_preconditions(mock_project, "test")
        assert can is True
        assert error is None
        assert warning is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_create_flow_service.py -v
```

**Step 3: Create service**

```python
"""CreateFlowService - business logic for branch/thread creation."""
from pathlib import Path

from ..domain.create_flow import CreateType
from ..magic_names import get_random_magic_name
from ..git_utils import sanitize_branch_name, max_branch_name_length, is_git_repo, has_uncommitted_changes


class CreateFlowService:
    """Business logic for branch/thread name selection flow."""

    def should_show_prompt(self, name_arg: str | None) -> bool:
        """Check if name prompt should be shown."""
        if name_arg is None:
            return True
        return not name_arg.strip()

    def get_magic_name(self, project) -> str:
        """Generate random magic name not used by project."""
        existing = {t.name for t in project.threads.values()}
        return get_random_magic_name(existing)

    def validate_name(self, name: str, project) -> tuple[str | None, str | None]:
        """Validate and sanitize name.

        Returns:
            (sanitized_name, None) on success
            (None, error_message) on failure
        """
        sanitized = sanitize_branch_name(name)
        if not sanitized:
            return None, "`[x]` Invalid name"

        max_len = max_branch_name_length(project.project_name)
        if len(sanitized) > max_len:
            return None, f"`[x]` Name too long (max {max_len} chars)"

        existing = {t.name for t in project.threads.values()}
        if sanitized in existing:
            return None, f"`[x]` Name `{sanitized}` already used"

        return sanitized, None

    def check_branch_preconditions(
        self, project, name: str
    ) -> tuple[bool, str | None, str | None]:
        """Check if branch can be created.

        Returns:
            (can_create, error, warning)
            - error: fatal, cannot proceed
            - warning: can proceed with user confirmation (e.g. uncommitted changes)
        """
        if not is_git_repo(Path(project.cwd)):
            return False, "`[x]` Git repository required", None

        if has_uncommitted_changes(Path(project.cwd)):
            return False, None, f"`[!]` Uncommitted changes"

        return True, None, None


# Module-level singleton
create_flow_service = CreateFlowService()
```

**Step 4: Run test**

```bash
pytest tests/test_create_flow_service.py -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/create_flow.py tests/test_create_flow_service.py
git commit -m "feat(services): add CreateFlowService with validation"
```

---

### Task 5: Create keyboard builder

**Files:**
- Create: `src/codogram/keyboards/create_flow.py`
- Test: `tests/test_create_flow_keyboard.py`

**Step 1: Write tests**

```python
"""Tests for create flow keyboard."""
import pytest
from codogram.keyboards.create_flow import (
    build_name_prompt_keyboard,
    CALLBACK_MAGIC_PREFIX,
    CALLBACK_CANCEL,
)
from codogram.domain.create_flow import CreateType


def test_keyboard_branch_buttons():
    kb = build_name_prompt_keyboard(CreateType.BRANCH)
    buttons = kb.inline_keyboard

    assert len(buttons) == 2
    assert buttons[0][0].text == "🔮 Magic name"
    assert buttons[0][0].callback_data == f"{CALLBACK_MAGIC_PREFIX}branch"
    assert buttons[1][0].text == "[<<] Go back"
    assert buttons[1][0].callback_data == CALLBACK_CANCEL


def test_keyboard_thread_buttons():
    kb = build_name_prompt_keyboard(CreateType.THREAD)
    buttons = kb.inline_keyboard

    assert buttons[0][0].callback_data == f"{CALLBACK_MAGIC_PREFIX}thread"


def test_callback_constants():
    """Callback data constants are defined."""
    assert CALLBACK_MAGIC_PREFIX == "create_magic:"
    assert CALLBACK_CANCEL == "create_cancel"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_create_flow_keyboard.py -v
```

**Step 3: Create keyboard module**

```python
"""Keyboards for create flow."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ..domain.create_flow import CreateType

# Callback data constants
CALLBACK_MAGIC_PREFIX = "create_magic:"
CALLBACK_CANCEL = "create_cancel"


def build_name_prompt_keyboard(create_type: CreateType) -> InlineKeyboardMarkup:
    """Build keyboard for name prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔮 Magic name",
            callback_data=f"{CALLBACK_MAGIC_PREFIX}{create_type.value}"
        )],
        [InlineKeyboardButton(
            text="[<<] Go back",
            callback_data=CALLBACK_CANCEL
        )],
    ])
```

**Step 4: Run test**

```bash
pytest tests/test_create_flow_keyboard.py -v
```

**Step 5: Commit**

```bash
git add src/codogram/keyboards/create_flow.py tests/test_create_flow_keyboard.py
git commit -m "feat(keyboards): add create flow keyboard builder"
```

---

### Task 6: Create handler for callbacks and name input

**Files:**
- Create: `src/codogram/handlers/create_flow.py`
- Test: `tests/test_create_flow_handler.py`

**Step 1: Write tests**

```python
"""Tests for create flow handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import CallbackQuery, Message, Chat

from codogram.handlers.common import set_flow_state, get_flow_state, clear_flow_state


@pytest.fixture
def mock_callback():
    cb = MagicMock(spec=CallbackQuery)
    cb.message = MagicMock(spec=Message)
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = -100123
    cb.message.message_thread_id = 456
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.message_thread_id = 456
    msg.text = "my-feature"
    msg.bot = MagicMock()
    return msg


@pytest.mark.asyncio
async def test_cancel_deletes_message_and_clears_state(mock_callback):
    """Cancel callback deletes prompt and clears state."""
    from codogram.handlers.create_flow import on_create_cancel

    mock_callback.data = "create_cancel"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name"})

    mock_queue = AsyncMock()

    await on_create_cancel(mock_callback, mock_queue)

    assert get_flow_state(-100123, 456) is None
    mock_queue.delete.assert_called_once_with(mock_callback.message)
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_magic_branch_creates_branch(mock_callback):
    """Magic name callback creates branch with random name."""
    from codogram.handlers.create_flow import on_create_magic

    mock_callback.data = "create_magic:branch"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "branch"})

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.threads = {}

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service, \
         patch("codogram.handlers.create_flow._do_create_branch") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.get_magic_name.return_value = "arcane"

        await on_create_magic(mock_callback, mock_queue)

        assert get_flow_state(-100123, 456) is None
        mock_queue.delete.assert_called_once()
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_handle_name_input_creates_branch(mock_message):
    """Text message creates branch when awaiting."""
    from codogram.handlers.create_flow import handle_name_input

    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "branch"})

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.threads = {}

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service, \
         patch("codogram.handlers.create_flow._do_create_branch") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.validate_name.return_value = ("my-feature", None)

        result = await handle_name_input(mock_message, mock_queue)

        assert result is True
        assert get_flow_state(-100123, 456) is None
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_handle_name_input_invalid_shows_error(mock_message):
    """Invalid name shows error."""
    from codogram.handlers.create_flow import handle_name_input

    mock_message.text = "!!!"
    set_flow_state(-100123, 456, {"type": "awaiting_create_name", "create_type": "branch"})

    mock_queue = AsyncMock()
    mock_project = MagicMock()

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.validate_name.return_value = (None, "`[x]` Invalid name")

        result = await handle_name_input(mock_message, mock_queue)

        assert result is True
        mock_queue.reply.assert_called_once()
        assert "Invalid" in mock_queue.reply.call_args[0][1]

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_handle_name_input_no_state_returns_false(mock_message):
    """Returns False if no awaiting state."""
    from codogram.handlers.create_flow import handle_name_input

    clear_flow_state(-100123, 456)

    mock_queue = AsyncMock()

    result = await handle_name_input(mock_message, mock_queue)

    assert result is False
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_create_flow_handler.py -v
```

**Step 3: Create handler**

```python
"""Handlers for create flow (branch/thread name selection)."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from ..domain.create_flow import CreateType
from ..handlers.common import get_flow_state, clear_flow_state
from ..keyboards.create_flow import CALLBACK_MAGIC_PREFIX, CALLBACK_CANCEL
from ..services.create_flow import create_flow_service
from ..services.branch import do_branch_create
from ..services.launch import create_thread_with_session
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from ..git_utils import get_default_branch

router = Router(name="create_flow")


@router.callback_query(F.data == CALLBACK_CANCEL)
async def on_create_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle cancel - delete prompt and clear state."""
    clear_flow_state(callback.message.chat.id, callback.message.message_thread_id)
    await telegram_queue.delete(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith(CALLBACK_MAGIC_PREFIX))
async def on_create_magic(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle magic name button - generate name and create."""
    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    type_str = callback.data.split(":")[1]
    create_type = CreateType(type_str)

    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    name = create_flow_service.get_magic_name(project)

    await telegram_queue.delete(callback.message)

    if create_type == CreateType.BRANCH:
        await _do_create_branch(callback.bot, chat_id, thread_id, project, name, telegram_queue)
    else:
        await _do_create_thread(callback.bot, chat_id, project, name, telegram_queue)

    await callback.answer()


async def handle_name_input(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Handle text message as name input.

    Returns True if message was handled, False if no awaiting state.
    """
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    state = get_flow_state(chat_id, thread_id)

    if not state or state.get("type") != "awaiting_create_name":
        return False

    create_type_str = state.get("create_type")
    clear_flow_state(chat_id, thread_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not found")
        return True

    name, error = create_flow_service.validate_name(message.text.strip(), project)
    if error:
        await telegram_queue.reply(message, error)
        return True

    create_type = CreateType(create_type_str)
    if create_type == CreateType.BRANCH:
        await _do_create_branch(message.bot, chat_id, thread_id, project, name, telegram_queue)
    else:
        await _do_create_thread(message.bot, chat_id, project, name, telegram_queue)

    return True


async def _do_create_branch(
    bot, chat_id: int, thread_id: int | None, project, name: str, telegram_queue: TelegramQueue
):
    """Create branch with given name, handling preconditions."""
    can_create, error, warning = create_flow_service.check_branch_preconditions(project, name)

    if error:
        await telegram_queue.send(chat_id, error, thread_id=thread_id)
        return

    if warning:
        # Uncommitted changes - show options
        default_branch = get_default_branch(project.cwd)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Create from last commit",
                callback_data=f"bc_create:{name}:{default_branch}"
            )],
            [InlineKeyboardButton(
                text="Commit first",
                callback_data=f"bc_commit:{name}"
            )],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")],
        ])
        await telegram_queue.send(chat_id, warning, thread_id=thread_id, reply_markup=keyboard)
        return

    default_branch = get_default_branch(project.cwd)
    await do_branch_create(bot, chat_id, project, name, default_branch)


async def _do_create_thread(bot, chat_id: int, project, name: str, telegram_queue: TelegramQueue):
    """Create thread with given name."""
    thread = await create_thread_with_session(
        bot=bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )
    if not thread:
        await telegram_queue.send(chat_id, "`[x]` Error creating topic")
```

**Step 4: Run test**

```bash
pytest tests/test_create_flow_handler.py -v
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/create_flow.py tests/test_create_flow_handler.py
git commit -m "feat(handlers): add create flow callbacks and name input"
```

---

### Task 7: Update /branch to show prompt

**Files:**
- Modify: `src/codogram/handlers/branches.py`
- Test: `tests/test_branch_prompt.py`

**Step 1: Write tests**

```python
"""Tests for /branch name prompt."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, Chat

from codogram.handlers.common import get_flow_state, clear_flow_state


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.chat.is_forum = True
    msg.message_thread_id = 456
    msg.text = "/branch"
    return msg


@pytest.mark.asyncio
async def test_branch_no_arg_shows_prompt(mock_message):
    """'/branch' without argument shows name prompt."""
    from codogram.handlers.branches import cmd_branch_create

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Branch name?" in call_args[0][1]

        state = get_flow_state(-100123, 456)
        assert state is not None
        assert state["type"] == "awaiting_create_name"
        assert state["create_type"] == "branch"

        clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_branch_with_arg_skips_prompt(mock_message):
    """'/branch mystic' validates and proceeds."""
    from codogram.handlers.branches import cmd_branch_create

    mock_message.text = "/branch mystic"
    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.project_name = "test"
    mock_project.threads = {}

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True), \
         patch("codogram.handlers.branches.create_flow_service") as mock_service, \
         patch("codogram.handlers.branches.branch_exists", return_value=False), \
         patch("codogram.handlers.branches.has_uncommitted_changes", return_value=False), \
         patch("codogram.handlers.branches.get_default_branch", return_value="main"), \
         patch("codogram.handlers.branches.do_branch_create"), \
         patch("pathlib.Path.exists", return_value=False):
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.should_show_prompt.return_value = False
        mock_service.validate_name.return_value = ("mystic", None)

        await cmd_branch_create(mock_message, mock_queue)

        assert get_flow_state(-100123, 456) is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_branch_prompt.py -v
```

**Step 3: Update branches.py**

Add imports and update `cmd_branch_create`:

```python
# Add imports at top
from ..domain.create_flow import CreateType
from ..handlers.common import set_flow_state
from ..keyboards.create_flow import build_name_prompt_keyboard
from ..services.create_flow import create_flow_service

# Update cmd_branch_create
@router.message(Command("branch_create"))
async def cmd_branch_create(message: Message, telegram_queue: TelegramQueue):
    """Create a new worktree branch with isolated Claude session."""
    if not await require_forum_group(message, telegram_queue):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not registered. Use /start first.")
        return

    if not is_git_repo(Path(project.cwd)):
        await telegram_queue.reply(message, "`[x]` Git repository required for /branch_create")
        return

    # Parse name argument
    args = message.text.split(maxsplit=1)
    name_arg = args[1].strip() if len(args) > 1 else None

    # No name - show prompt
    if create_flow_service.should_show_prompt(name_arg):
        set_flow_state(message.chat.id, message.message_thread_id, {
            "type": "awaiting_create_name",
            "create_type": "branch",
        })
        await telegram_queue.reply(
            message,
            "Branch name?\n\nSend name or pick random",
            reply_markup=build_name_prompt_keyboard(CreateType.BRANCH),
        )
        return

    # Validate name
    branch_name, error = create_flow_service.validate_name(name_arg, project)
    if error:
        await telegram_queue.reply(message, error)
        return

    # Continue with existing logic (branch_exists, worktree dir, uncommitted...)
    # ... rest of existing code ...
```

**Step 4: Run test**

```bash
pytest tests/test_branch_prompt.py -v
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/branches.py tests/test_branch_prompt.py
git commit -m "feat(branch): show name prompt when no argument"
```

---

### Task 8: Update /thread to show prompt

**Files:**
- Modify: `src/codogram/handlers/threads.py`
- Test: `tests/test_thread_prompt.py`

**Step 1: Write tests**

```python
"""Tests for /thread name prompt."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, Chat

from codogram.handlers.common import get_flow_state, clear_flow_state


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.chat.is_forum = True
    msg.message_thread_id = 456
    msg.text = "/thread"
    return msg


@pytest.mark.asyncio
async def test_thread_no_arg_shows_prompt(mock_message):
    """'/thread' without argument shows name prompt."""
    from codogram.handlers.threads import cmd_thread_create

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.threads = {}

    with patch("codogram.handlers.threads.project_manager") as mock_pm:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_thread_create(mock_message, mock_queue)

        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Thread name?" in call_args[0][1]

        state = get_flow_state(-100123, 456)
        assert state is not None
        assert state["type"] == "awaiting_create_name"
        assert state["create_type"] == "thread"

        clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_thread_with_arg_creates(mock_message):
    """'/thread mystic' creates thread directly."""
    from codogram.handlers.threads import cmd_thread_create

    mock_message.text = "/thread mystic"
    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.threads = {}

    with patch("codogram.handlers.threads.project_manager") as mock_pm, \
         patch("codogram.handlers.threads.create_flow_service") as mock_service, \
         patch("codogram.handlers.threads.create_thread_with_session") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.should_show_prompt.return_value = False
        mock_service.validate_name.return_value = ("mystic", None)
        mock_create.return_value = MagicMock()

        await cmd_thread_create(mock_message, mock_queue)

        assert get_flow_state(-100123, 456) is None
        mock_create.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_thread_prompt.py -v
```

**Step 3: Update threads.py**

Remove old `_flow_state` import, add new imports:

```python
# Update imports
from ..domain.create_flow import CreateType
from ..handlers.common import require_forum_group, set_flow_state, get_flow_state, clear_flow_state
from ..keyboards.create_flow import build_name_prompt_keyboard
from ..services.create_flow import create_flow_service

# Update cmd_thread_create
@router.message(Command("thread_create"))
async def cmd_thread_create(message: Message, telegram_queue: TelegramQueue):
    """Create a new thread (topic) with its own Claude session."""
    if not await require_forum_group(message, telegram_queue):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "Project not found. Use /start first")
        return

    # Parse optional name
    args = message.text.split(maxsplit=1)
    name_arg = args[1].strip() if len(args) > 1 else None

    # No name - show prompt
    if create_flow_service.should_show_prompt(name_arg):
        set_flow_state(chat_id, thread_id, {
            "type": "awaiting_create_name",
            "create_type": "thread",
        })
        await telegram_queue.reply(
            message,
            "Thread name?\n\nSend name or pick random",
            reply_markup=build_name_prompt_keyboard(CreateType.THREAD),
        )
        return

    # Validate name
    name, error = create_flow_service.validate_name(name_arg, project)
    if error:
        await telegram_queue.reply(message, error)
        return

    # Create thread (existing logic for non-worktree confirmation can stay)
    # ... rest of existing code ...
```

**Step 4: Update thread_create_pending flow**

Also update `thread_create_pending` to use new state functions:

```python
# In confirmation section, use new state functions:
set_flow_state(chat_id, thread_id, {
    "type": "thread_create_pending",
    "name": name,
})
```

**Step 5: Run test**

```bash
pytest tests/test_thread_prompt.py -v
```

**Step 6: Commit**

```bash
git add src/codogram/handlers/threads.py tests/test_thread_prompt.py
git commit -m "feat(thread): show name prompt when no argument"
```

---

### Task 9: Update messages.py to intercept name input

**Files:**
- Modify: `src/codogram/handlers/messages.py`
- Test: existing tests should cover

**Step 1: Update messages.py**

Add at beginning of `on_message`, after command skip:

```python
from .create_flow import handle_name_input

@router.message()
async def on_message(message: Message, telegram_queue: TelegramQueue):
    text = message.text
    if not text:
        return

    # ... logging ...

    # Skip commands
    if text.startswith("/"):
        return

    chat_id = message.chat.id

    # Check if awaiting name input for create flow
    if await handle_name_input(message, telegram_queue):
        return

    # Normal routing...
    thread_id = message.message_thread_id
    result = _message_router.route(chat_id, thread_id, text)
    # ... rest unchanged ...
```

**Step 2: Run all tests**

```bash
pytest -v
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/messages.py
git commit -m "feat(messages): intercept name input for create flow"
```

---

### Task 10: Register create_flow router

**Files:**
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Check current router registration**

Read file to understand pattern.

**Step 2: Add create_flow router**

Import and register before messages router (order matters):

```python
from .create_flow import router as create_flow_router

# In setup function or __all__:
# Register create_flow before messages
```

**Step 3: Run all tests**

```bash
pytest -v
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/__init__.py
git commit -m "feat(handlers): register create_flow router"
```

---

### Task 11: Run full test suite and fix issues

**Step 1: Run all tests**

```bash
pytest -v
```

**Step 2: Fix any failures**

**Step 3: Commit fixes**

```bash
git add -A
git commit -m "fix: test suite fixes"
```

---

### Task 12: Manual E2E test

**Reference:** `docs/e2e/CLAUDE.md`

**Step 1: Ask user for test chat ID**

**Step 2: Start bot from worktree**

```bash
./dev-run.sh
```

**Step 3: Test /branch without arg**

```
send_message(chat_id, "/branch")
# Expect: "Branch name?" with buttons
```

**Step 4: Test cancel**

```
press_inline_button(chat_id, button_text="[<<] Go back")
# Expect: message deleted
```

**Step 5: Test magic name**

```
send_message(chat_id, "/branch")
press_inline_button(chat_id, button_text="🔮 Magic name")
# Expect: branch created with random name
```

**Step 6: Test text input**

```
send_message(chat_id, "/thread")
send_message(chat_id, "test-feature")
# Expect: thread created with name "test-feature"
```

**Step 7: Test command clears state**

```
send_message(chat_id, "/branch")
send_message(chat_id, "/help")
send_message(chat_id, "my-name")
# Expect: "my-name" goes to tmux, NOT creates branch
```

**Step 8: Test with argument (unchanged)**

```
send_message(chat_id, "/branch direct-name")
# Expect: branch created directly, no prompt
```

---

### Task 13: Update docs

**Files:**
- Modify: `docs/ROADMAP.md`
- Move: design to done

**Step 1: Update ROADMAP**

Move "Thread create UX" from Backlog to Done:

```markdown
### Thread/Branch create UX
Interactive name selection for `/branch` and `/thread`:
- Without argument → show prompt with [🔮 Magic name] button
- User can send custom name as text message
- With argument → create directly (unchanged)
- Unified validation rules for both commands
- Middleware clears state on any command (prevents stale prompts)
- State keyed by (chat_id, thread_id) for multi-topic support
- See [docs/designs/done/2026-01-07-thread-branch-create-ux.md](designs/done/2026-01-07-thread-branch-create-ux.md)
```

**Step 2: Move design**

```bash
mkdir -p docs/designs/done
mv docs/designs/2026-01-07-thread-branch-create-ux.md docs/designs/done/
```

**Step 3: Commit**

```bash
git add docs/
git commit -m "docs: mark thread/branch create UX as done"
```
