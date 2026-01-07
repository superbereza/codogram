# Thread/Branch Create UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show name selection prompt when `/branch` or `/thread` called without argument instead of auto-creating with random name.

**Architecture:** Layered approach - domain types in `domain/create_flow.py`, business logic in `services/create_flow.py`, thin handlers that delegate to service.

**Tech Stack:** aiogram, existing `sanitize_branch_name`, `get_random_magic_name`

---

### Task 1: Create domain types

**Files:**
- Create: `src/codogram/domain/create_flow.py`
- Test: `tests/test_create_flow_domain.py`

**Step 1: Write tests**

```python
"""Tests for create flow domain types."""
import pytest
from codogram.domain.create_flow import (
    CreateType,
    CreateFlowState,
    get_state,
    set_state,
    clear_state,
    has_pending_create,
)


def test_create_type_values():
    assert CreateType.BRANCH.value == "branch"
    assert CreateType.THREAD.value == "thread"


def test_set_and_get_state():
    set_state(123, CreateFlowState(CreateType.BRANCH, thread_id=456))
    state = get_state(123)
    assert state is not None
    assert state.type == CreateType.BRANCH
    assert state.thread_id == 456
    clear_state(123)


def test_get_state_returns_none_when_empty():
    clear_state(999)
    assert get_state(999) is None


def test_clear_state():
    set_state(123, CreateFlowState(CreateType.THREAD, None))
    clear_state(123)
    assert get_state(123) is None


def test_has_pending_create():
    clear_state(123)
    assert has_pending_create(123) is False
    set_state(123, CreateFlowState(CreateType.BRANCH, None))
    assert has_pending_create(123) is True
    clear_state(123)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_create_flow_domain.py -v
```

**Step 3: Create domain module**

```python
"""Domain types for create flow (branch/thread)."""
from dataclasses import dataclass
from enum import Enum


class CreateType(Enum):
    """Type of entity to create."""
    BRANCH = "branch"
    THREAD = "thread"


@dataclass
class CreateFlowState:
    """State for pending create flow."""
    type: CreateType
    thread_id: int | None  # Telegram thread where command was issued


# Module-level state storage
_create_state: dict[int, CreateFlowState] = {}


def get_state(chat_id: int) -> CreateFlowState | None:
    """Get pending create state for chat."""
    return _create_state.get(chat_id)


def set_state(chat_id: int, state: CreateFlowState) -> None:
    """Set pending create state for chat."""
    _create_state[chat_id] = state


def clear_state(chat_id: int) -> None:
    """Clear pending create state for chat."""
    _create_state.pop(chat_id, None)


def has_pending_create(chat_id: int) -> bool:
    """Check if chat has pending create flow."""
    return chat_id in _create_state
```

**Step 4: Run test**

```bash
pytest tests/test_create_flow_domain.py -v
```

**Step 5: Commit**

```bash
git add src/codogram/domain/create_flow.py tests/test_create_flow_domain.py
git commit -m "feat(domain): add create flow state types"
```

---

### Task 2: Create service with validation

**Files:**
- Create: `src/codogram/services/create_flow.py`
- Test: `tests/test_create_flow_service.py`

**Step 1: Write tests**

```python
"""Tests for create flow service."""
import pytest
from unittest.mock import MagicMock

from codogram.services.create_flow import CreateFlowService
from codogram.domain.create_flow import CreateType


@pytest.fixture
def service():
    return CreateFlowService()


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.project_name = "testproject"
    project.threads = {}
    return project


def test_should_show_prompt_no_name(service):
    assert service.should_show_prompt(None) is True


def test_should_show_prompt_with_name(service):
    assert service.should_show_prompt("mystic") is False


def test_should_show_prompt_empty_string(service):
    """Empty string treated as no name."""
    assert service.should_show_prompt("") is True


def test_get_magic_name(service, mock_project):
    name = service.get_magic_name(mock_project)
    assert name is not None
    assert len(name) > 0


def test_get_magic_name_excludes_existing(service, mock_project):
    """Magic name should not match existing thread names."""
    existing_thread = MagicMock()
    existing_thread.name = "arcane"
    mock_project.threads = {1: existing_thread}

    # Generate 10 names, none should be "arcane"
    names = [service.get_magic_name(mock_project) for _ in range(10)]
    assert "arcane" not in names


def test_validate_name_success(service, mock_project):
    name, error = service.validate_name("my-feature", mock_project, CreateType.BRANCH)
    assert error is None
    assert name == "my-feature"


def test_validate_name_sanitizes(service, mock_project):
    """Spaces converted to dashes, lowercase."""
    name, error = service.validate_name("My Feature", mock_project, CreateType.BRANCH)
    assert error is None
    assert name == "my-feature"


def test_validate_name_empty_after_sanitize(service, mock_project):
    """Invalid chars only results in empty name."""
    name, error = service.validate_name("!!!", mock_project, CreateType.BRANCH)
    assert name is None
    assert "Invalid" in error


def test_validate_name_too_long(service, mock_project):
    """Name exceeding max length rejected."""
    long_name = "a" * 100
    name, error = service.validate_name(long_name, mock_project, CreateType.BRANCH)
    assert name is None
    assert "too long" in error


def test_validate_name_already_exists(service, mock_project):
    """Name matching existing thread rejected."""
    existing = MagicMock()
    existing.name = "mystic"
    mock_project.threads = {1: existing}

    name, error = service.validate_name("mystic", mock_project, CreateType.THREAD)
    assert name is None
    assert "already used" in error
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_create_flow_service.py -v
```

**Step 3: Create service**

```python
"""CreateFlowService - business logic for branch/thread creation."""
from ..domain.create_flow import CreateType
from ..magic_names import get_random_magic_name
from ..git_utils import sanitize_branch_name, max_branch_name_length


class CreateFlowService:
    """Business logic for branch/thread name selection flow."""

    def should_show_prompt(self, name_arg: str | None) -> bool:
        """Check if name prompt should be shown."""
        return not name_arg

    def get_magic_name(self, project) -> str:
        """Generate random magic name not used by project."""
        existing = {t.name for t in project.threads.values()}
        return get_random_magic_name(existing)

    def validate_name(
        self,
        name: str,
        project,
        create_type: CreateType,
    ) -> tuple[str | None, str | None]:
        """Validate and sanitize name.

        Returns:
            (sanitized_name, None) on success
            (None, error_message) on failure
        """
        # Sanitize
        sanitized = sanitize_branch_name(name)
        if not sanitized:
            return None, "`[x]` Invalid name"

        # Check length
        max_len = max_branch_name_length(project.project_name)
        if len(sanitized) > max_len:
            return None, f"`[x]` Name too long (max {max_len} chars)"

        # Check uniqueness
        existing = {t.name for t in project.threads.values()}
        if sanitized in existing:
            return None, f"`[x]` Name `{sanitized}` already used"

        return sanitized, None
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

### Task 3: Create keyboard builder

**Files:**
- Create: `src/codogram/keyboards/create_flow.py`
- Test: `tests/test_create_flow_keyboard.py`

**Step 1: Write tests**

```python
"""Tests for create flow keyboard."""
import pytest
from codogram.keyboards.create_flow import build_name_prompt_keyboard
from codogram.domain.create_flow import CreateType


def test_keyboard_branch_buttons():
    kb = build_name_prompt_keyboard(CreateType.BRANCH)
    buttons = kb.inline_keyboard

    assert len(buttons) == 2
    assert buttons[0][0].text == "🔮 Magic name"
    assert buttons[0][0].callback_data == "create_magic:branch"
    assert buttons[1][0].text == "[<<] Go back"
    assert buttons[1][0].callback_data == "create_cancel"


def test_keyboard_thread_buttons():
    kb = build_name_prompt_keyboard(CreateType.THREAD)
    buttons = kb.inline_keyboard

    assert buttons[0][0].callback_data == "create_magic:thread"
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


def build_name_prompt_keyboard(create_type: CreateType) -> InlineKeyboardMarkup:
    """Build keyboard for name prompt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔮 Magic name",
            callback_data=f"create_magic:{create_type.value}"
        )],
        [InlineKeyboardButton(
            text="[<<] Go back",
            callback_data="create_cancel"
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

### Task 4: Create shared handler for callbacks

**Files:**
- Create: `src/codogram/handlers/create_flow.py`
- Test: `tests/test_create_flow_handler.py`

**Step 1: Write tests**

```python
"""Tests for create flow handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import CallbackQuery, Message, Chat


@pytest.fixture
def mock_callback():
    cb = MagicMock(spec=CallbackQuery)
    cb.message = MagicMock(spec=Message)
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = -100123
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


@pytest.mark.asyncio
async def test_cancel_deletes_message_and_clears_state(mock_callback):
    """Cancel callback deletes prompt and clears state."""
    from codogram.handlers.create_flow import on_create_cancel
    from codogram.domain.create_flow import set_state, get_state, CreateFlowState, CreateType

    mock_callback.data = "create_cancel"
    set_state(-100123, CreateFlowState(CreateType.BRANCH, None))

    mock_queue = AsyncMock()

    await on_create_cancel(mock_callback, mock_queue)

    assert get_state(-100123) is None
    mock_queue.delete.assert_called_once_with(mock_callback.message)
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_magic_branch_creates_branch(mock_callback):
    """Magic name callback creates branch with random name."""
    from codogram.handlers.create_flow import on_create_magic
    from codogram.domain.create_flow import set_state, get_state, CreateFlowState, CreateType

    mock_callback.data = "create_magic:branch"
    set_state(-100123, CreateFlowState(CreateType.BRANCH, thread_id=456))

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.threads = {}

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service, \
         patch("codogram.handlers.create_flow.do_branch_create") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.get_magic_name.return_value = "arcane"
        mock_service.validate_name.return_value = ("arcane", None)

        await on_create_magic(mock_callback, mock_queue)

        # State cleared
        assert get_state(-100123) is None

        # Message deleted
        mock_queue.delete.assert_called_once()

        # Branch creation initiated
        mock_create.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_create_flow_handler.py -v
```

**Step 3: Create handler**

```python
"""Shared handlers for create flow (branch/thread)."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..domain.create_flow import CreateType, get_state, clear_state
from ..services.create_flow import CreateFlowService
from ..services.branch import do_branch_create
from ..services.launch import create_thread_with_session
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue
from ..git_utils import get_default_branch, has_uncommitted_changes, is_git_repo
from pathlib import Path

router = Router(name="create_flow")

# Service instance
create_flow_service = CreateFlowService()


@router.callback_query(F.data == "create_cancel")
async def on_create_cancel(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle cancel - delete prompt and clear state."""
    clear_state(callback.message.chat.id)
    await telegram_queue.delete(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("create_magic:"))
async def on_create_magic(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle magic name button - generate name and create."""
    chat_id = callback.message.chat.id
    type_str = callback.data.split(":")[1]
    create_type = CreateType(type_str)

    state = get_state(chat_id)
    thread_id = state.thread_id if state else callback.message.message_thread_id
    clear_state(chat_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    # Generate magic name
    name = create_flow_service.get_magic_name(project)

    # Delete prompt
    await telegram_queue.delete(callback.message)

    # Create entity
    if create_type == CreateType.BRANCH:
        await _create_branch(callback.bot, chat_id, project, name, thread_id, telegram_queue)
    else:
        await _create_thread(callback.bot, chat_id, project, name, telegram_queue)

    await callback.answer()


async def _create_branch(bot, chat_id: int, project, name: str, thread_id: int | None, telegram_queue: TelegramQueue):
    """Create branch with given name."""
    # Validate git repo
    if not is_git_repo(Path(project.cwd)):
        await telegram_queue.send(chat_id, "`[x]` Git repository required", thread_id=thread_id)
        return

    default_branch = get_default_branch(Path(project.cwd))

    # Check uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        await telegram_queue.send(
            chat_id,
            f"`[!]` Uncommitted changes. Commit first, then run `/branch {name}`",
            thread_id=thread_id,
        )
        return

    await do_branch_create(bot, chat_id, project, name, default_branch)


async def _create_thread(bot, chat_id: int, project, name: str, telegram_queue: TelegramQueue):
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
git commit -m "feat(handlers): add create flow callbacks"
```

---

### Task 5: Update /branch to show prompt

**Files:**
- Modify: `src/codogram/handlers/branches.py`
- Test: `tests/test_branch_prompt.py`

**Step 1: Write tests**

```python
"""Tests for /branch name prompt."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, Chat


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.chat.is_forum = True
    msg.message_thread_id = None
    msg.text = "/branch"
    return msg


@pytest.mark.asyncio
async def test_branch_no_arg_shows_prompt(mock_message):
    """'/branch' without argument shows name prompt."""
    from codogram.handlers.branches import cmd_branch_create
    from codogram.domain.create_flow import get_state, clear_state, CreateType

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        # Shows prompt
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Branch name?" in call_args[0][1]

        # Sets state
        state = get_state(-100123)
        assert state is not None
        assert state.type == CreateType.BRANCH

        clear_state(-100123)


@pytest.mark.asyncio
async def test_branch_with_arg_skips_prompt(mock_message):
    """'/branch mystic' skips prompt."""
    from codogram.handlers.branches import cmd_branch_create
    from codogram.domain.create_flow import get_state, clear_state

    mock_message.text = "/branch mystic"
    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.project_name = "test"
    mock_project.threads = {}

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True), \
         patch("codogram.handlers.branches.branch_exists", return_value=False), \
         patch("codogram.handlers.branches.has_uncommitted_changes", return_value=False), \
         patch("codogram.handlers.branches.get_default_branch", return_value="main"), \
         patch("codogram.handlers.branches.do_branch_create"), \
         patch("pathlib.Path.exists", return_value=False):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        # No prompt state
        assert get_state(-100123) is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_branch_prompt.py -v
```

**Step 3: Update branches.py**

Add imports at top:

```python
from ..domain.create_flow import CreateType, CreateFlowState, set_state
from ..keyboards.create_flow import build_name_prompt_keyboard
from ..services.create_flow import CreateFlowService

create_flow_service = CreateFlowService()
```

Update `cmd_branch_create`:

```python
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
        set_state(message.chat.id, CreateFlowState(CreateType.BRANCH, message.message_thread_id))
        await telegram_queue.reply(
            message,
            "Branch name?\n\nSend name or pick random",
            reply_markup=build_name_prompt_keyboard(CreateType.BRANCH),
        )
        return

    # Validate name
    branch_name, error = create_flow_service.validate_name(name_arg, project, CreateType.BRANCH)
    if error:
        await telegram_queue.reply(message, error)
        return

    # Rest unchanged - check branch_exists, worktree dir, uncommitted changes...
    # ... existing code ...
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

### Task 6: Update /thread to show prompt

**Files:**
- Modify: `src/codogram/handlers/threads.py`
- Test: `tests/test_thread_prompt.py`

**Step 1: Write tests**

```python
"""Tests for /thread name prompt."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, Chat


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.chat.is_forum = True
    msg.message_thread_id = None
    msg.text = "/thread"
    return msg


@pytest.mark.asyncio
async def test_thread_no_arg_shows_prompt(mock_message):
    """'/thread' without argument shows name prompt."""
    from codogram.handlers.threads import cmd_thread_create
    from codogram.domain.create_flow import get_state, clear_state, CreateType

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.threads = {}

    with patch("codogram.handlers.threads.project_manager") as mock_pm:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_thread_create(mock_message, mock_queue)

        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Thread name?" in call_args[0][1]

        state = get_state(-100123)
        assert state is not None
        assert state.type == CreateType.THREAD

        clear_state(-100123)


@pytest.mark.asyncio
async def test_thread_with_arg_skips_prompt(mock_message):
    """'/thread mystic' skips prompt."""
    from codogram.handlers.threads import cmd_thread_create
    from codogram.domain.create_flow import get_state

    mock_message.text = "/thread mystic"
    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.threads = {}

    with patch("codogram.handlers.threads.project_manager") as mock_pm, \
         patch("codogram.handlers.threads.create_thread_with_session") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_create.return_value = MagicMock()

        await cmd_thread_create(mock_message, mock_queue)

        assert get_state(-100123) is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_thread_prompt.py -v
```

**Step 3: Update threads.py**

Add imports:

```python
from ..domain.create_flow import CreateType, CreateFlowState, set_state
from ..keyboards.create_flow import build_name_prompt_keyboard
from ..services.create_flow import CreateFlowService

create_flow_service = CreateFlowService()
```

Update `cmd_thread_create`:

```python
@router.message(Command("thread_create"))
async def cmd_thread_create(message: Message, telegram_queue: TelegramQueue):
    """Create a new thread (topic) with its own Claude session."""
    if not await require_forum_group(message, telegram_queue):
        return

    chat_id = message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "Project not found. Use /start first")
        return

    # Parse optional name
    args = message.text.split(maxsplit=1)
    name_arg = args[1].strip() if len(args) > 1 else None

    # No name - show prompt
    if create_flow_service.should_show_prompt(name_arg):
        set_state(chat_id, CreateFlowState(CreateType.THREAD, message.message_thread_id))
        await telegram_queue.reply(
            message,
            "Thread name?\n\nSend name or pick random",
            reply_markup=build_name_prompt_keyboard(CreateType.THREAD),
        )
        return

    # Validate name
    name, error = create_flow_service.validate_name(name_arg, project, CreateType.THREAD)
    if error:
        await telegram_queue.reply(message, error)
        return

    # Check non-worktree threads (existing logic)
    non_worktree_threads = [
        t for t in project.threads.values()
        if t.thread_id is not None and not t.worktree_path
    ]

    if non_worktree_threads:
        # Store pending (existing confirmation flow)
        _flow_state[chat_id] = {
            "state": "thread_create_pending",
            "name": name,
        }
        # ... existing keyboard and message ...
        return

    # Create directly
    thread = await create_thread_with_session(
        bot=message.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    if not thread:
        await telegram_queue.reply(message, "Error creating topic")
```

**Step 4: Run test**

```bash
pytest tests/test_thread_prompt.py -v
```

**Step 5: Commit**

```bash
git add src/codogram/handlers/threads.py tests/test_thread_prompt.py
git commit -m "feat(thread): show name prompt when no argument"
```

---

### Task 7: Handle text input as name

**Files:**
- Modify: `src/codogram/handlers/messages.py`
- Modify: `src/codogram/handlers/create_flow.py`
- Test: `tests/test_name_text_input.py`

**Step 1: Write tests**

```python
"""Tests for text input as branch/thread name."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, Chat


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.message_thread_id = None
    msg.text = "my-feature"
    msg.from_user = MagicMock()
    msg.from_user.id = 123
    msg.bot = MagicMock()
    return msg


@pytest.mark.asyncio
async def test_text_used_as_branch_name(mock_message):
    """Text message creates branch when awaiting branch name."""
    from codogram.handlers.create_flow import handle_name_input
    from codogram.domain.create_flow import set_state, get_state, CreateFlowState, CreateType

    set_state(-100123, CreateFlowState(CreateType.BRANCH, thread_id=None))

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.project_name = "test"
    mock_project.threads = {}

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service, \
         patch("codogram.handlers.create_flow._create_branch") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.validate_name.return_value = ("my-feature", None)

        result = await handle_name_input(mock_message, mock_queue)

        assert result is True  # Handled
        assert get_state(-100123) is None  # State cleared
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_invalid_name_shows_error(mock_message):
    """Invalid name shows error and clears state."""
    from codogram.handlers.create_flow import handle_name_input
    from codogram.domain.create_flow import set_state, get_state, CreateFlowState, CreateType

    mock_message.text = "!!!"
    set_state(-100123, CreateFlowState(CreateType.BRANCH, thread_id=None))

    mock_queue = AsyncMock()
    mock_project = MagicMock()

    with patch("codogram.handlers.create_flow.project_manager") as mock_pm, \
         patch("codogram.handlers.create_flow.create_flow_service") as mock_service:
        mock_pm.get_by_chat.return_value = mock_project
        mock_service.validate_name.return_value = (None, "`[x]` Invalid name")

        result = await handle_name_input(mock_message, mock_queue)

        assert result is True
        assert get_state(-100123) is None
        mock_queue.reply.assert_called_once()
        assert "Invalid" in mock_queue.reply.call_args[0][1]
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_name_text_input.py -v
```

**Step 3: Add handle_name_input to create_flow.py**

```python
async def handle_name_input(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Handle text message as name input.

    Returns True if message was handled (state existed), False otherwise.
    """
    chat_id = message.chat.id
    state = get_state(chat_id)

    if not state:
        return False

    clear_state(chat_id)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not found")
        return True

    # Validate name
    name, error = create_flow_service.validate_name(message.text.strip(), project, state.type)
    if error:
        await telegram_queue.reply(message, error)
        return True

    # Create entity
    if state.type == CreateType.BRANCH:
        await _create_branch(message.bot, chat_id, project, name, state.thread_id, telegram_queue)
    else:
        await _create_thread(message.bot, chat_id, project, name, telegram_queue)

    return True
```

**Step 4: Update messages.py**

Add at top of `on_message`, after command skip:

```python
from .create_flow import handle_name_input
from ..domain.create_flow import has_pending_create

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

    # Check if awaiting name input
    if has_pending_create(chat_id):
        from .create_flow import handle_name_input
        if await handle_name_input(message, telegram_queue):
            return

    # Normal routing...
    # ... rest unchanged ...
```

**Step 5: Run test**

```bash
pytest tests/test_name_text_input.py -v
```

**Step 6: Commit**

```bash
git add src/codogram/handlers/create_flow.py src/codogram/handlers/messages.py tests/test_name_text_input.py
git commit -m "feat(messages): handle text input as branch/thread name"
```

---

### Task 8: Register create_flow router

**Files:**
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Check current init**

Read file to see router registration pattern.

**Step 2: Add import**

```python
from .create_flow import router as create_flow_router
```

Add to `__all__` and register in appropriate order (before messages router).

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

### Task 9: Run full test suite

**Step 1: Run all tests**

```bash
pytest -v
```

**Step 2: Fix any failures**

**Step 3: Commit fixes if any**

```bash
git add -A
git commit -m "fix: test suite fixes"
```

---

### Task 10: Manual E2E test

**Reference:** `docs/e2e/CLAUDE.md`

**Step 1: Ask user for test chat ID**

**Step 2: Restart bot**

```bash
./restart.sh
```

**Step 3: Test /branch without arg**

```
send_message(chat_id, "/branch")
# Expect: "Branch name?" with [🔮 Magic name] [<<] Go back]
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

**Step 7: Test with argument (unchanged)**

```
send_message(chat_id, "/branch direct-name")
# Expect: branch created directly, no prompt
```

---

### Task 11: Update docs

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
- See [docs/designs/done/2026-01-07-thread-branch-create-ux.md](designs/done/2026-01-07-thread-branch-create-ux.md)
```

**Step 2: Move design**

```bash
mv docs/designs/2026-01-07-thread-branch-create-ux.md docs/designs/done/
```

**Step 3: Commit**

```bash
git add docs/
git commit -m "docs: mark thread/branch create UX as done"
```
