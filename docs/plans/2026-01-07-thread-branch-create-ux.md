# Thread/Branch Create UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show name selection prompt when `/branch` or `/thread` called without argument instead of auto-creating with random name.

**Architecture:** Add `awaiting_branch_name` / `awaiting_thread_name` state to `_flow_state`. Intercept messages in `messages.py` before routing to tmux. Reuse existing `sanitize_branch_name` and validation logic.

**Tech Stack:** aiogram, existing `_flow_state` dict, `git_utils.sanitize_branch_name`

---

### Task 1: Add name prompt helper to common.py

**Files:**
- Modify: `src/codogram/handlers/common.py`
- Test: `tests/test_name_prompt.py` (new)

**Step 1: Write the failing test**

Create `tests/test_name_prompt.py`:

```python
"""Tests for name prompt flow."""
import pytest
from codogram.handlers.common import build_name_prompt_keyboard, NAME_FLOW_STATES


def test_build_name_prompt_keyboard_branch():
    """Keyboard for branch has correct buttons."""
    kb = build_name_prompt_keyboard("branch")
    buttons = kb.inline_keyboard

    assert len(buttons) == 2  # Two rows
    assert buttons[0][0].text == "🔮 Magic name"
    assert buttons[0][0].callback_data == "magic_name:branch"
    assert buttons[1][0].text == "[<<] Go back"
    assert buttons[1][0].callback_data == "cancel_name_prompt"


def test_build_name_prompt_keyboard_thread():
    """Keyboard for thread has correct buttons."""
    kb = build_name_prompt_keyboard("thread")
    buttons = kb.inline_keyboard

    assert buttons[0][0].callback_data == "magic_name:thread"


def test_name_flow_states_defined():
    """Flow states constants are defined."""
    assert "awaiting_branch_name" in NAME_FLOW_STATES
    assert "awaiting_thread_name" in NAME_FLOW_STATES
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_name_prompt.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add to `src/codogram/handlers/common.py`:

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Flow states for name input
NAME_FLOW_STATES = {"awaiting_branch_name", "awaiting_thread_name"}


def build_name_prompt_keyboard(prompt_type: str) -> InlineKeyboardMarkup:
    """Build keyboard for branch/thread name prompt.

    Args:
        prompt_type: "branch" or "thread"
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔮 Magic name", callback_data=f"magic_name:{prompt_type}")],
        [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel_name_prompt")],
    ])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_name_prompt.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/common.py tests/test_name_prompt.py
git commit -m "feat(handlers): add name prompt keyboard builder"
```

---

### Task 2: Add cancel_name_prompt callback

**Files:**
- Modify: `src/codogram/handlers/common.py`
- Modify: `tests/test_name_prompt.py`

**Step 1: Write the failing test**

Add to `tests/test_name_prompt.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import CallbackQuery, Message, Chat


@pytest.fixture
def mock_callback():
    cb = MagicMock(spec=CallbackQuery)
    cb.message = MagicMock(spec=Message)
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = -100123
    cb.data = "cancel_name_prompt"
    cb.answer = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_cancel_name_prompt_clears_state(mock_callback):
    """Cancel clears flow state and deletes message."""
    from codogram.handlers.common import cb_cancel_name_prompt, _flow_state

    mock_queue = AsyncMock()
    _flow_state[-100123] = {"state": "awaiting_branch_name"}

    await cb_cancel_name_prompt(mock_callback, mock_queue)

    assert -100123 not in _flow_state
    mock_queue.delete.assert_called_once_with(mock_callback.message)
    mock_callback.answer.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_name_prompt.py::test_cancel_name_prompt_clears_state -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add to `src/codogram/handlers/common.py`:

```python
@router.callback_query(F.data == "cancel_name_prompt")
async def cb_cancel_name_prompt(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle cancel for name prompt - just delete the message."""
    chat_id = callback.message.chat.id
    _flow_state.pop(chat_id, None)
    await telegram_queue.delete(callback.message)
    await callback.answer()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_name_prompt.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/common.py tests/test_name_prompt.py
git commit -m "feat(handlers): add cancel_name_prompt callback"
```

---

### Task 3: Update /branch to show name prompt

**Files:**
- Modify: `src/codogram/handlers/branches.py`
- Test: `tests/test_branch_name_prompt.py` (new)

**Step 1: Write the failing test**

Create `tests/test_branch_name_prompt.py`:

```python
"""Tests for /branch name prompt flow."""
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
    msg.text = "/branch"  # No argument
    return msg


@pytest.mark.asyncio
async def test_branch_without_arg_shows_name_prompt(mock_message):
    """'/branch' without argument shows name prompt."""
    from codogram.handlers.branches import cmd_branch_create
    from codogram.handlers.common import _flow_state

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.threads = {}

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        # Should show prompt
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Branch name?" in call_args[0][1]
        assert "reply_markup" in call_args[1]

        # Should set flow state
        assert _flow_state[-100123]["state"] == "awaiting_branch_name"

    # Cleanup
    _flow_state.pop(-100123, None)


@pytest.mark.asyncio
async def test_branch_with_arg_creates_directly(mock_message):
    """'/branch mystic' creates branch directly without prompt."""
    from codogram.handlers.branches import cmd_branch_create
    from codogram.handlers.common import _flow_state

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
         patch("codogram.handlers.branches.do_branch_create") as mock_create, \
         patch("pathlib.Path.exists", return_value=False):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        # Should NOT set flow state
        assert -100123 not in _flow_state

        # Should call do_branch_create
        mock_create.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_branch_name_prompt.py -v`
Expected: FAIL (current code auto-generates name)

**Step 3: Modify branches.py**

In `src/codogram/handlers/branches.py`, update `cmd_branch_create`:

```python
from .common import _flow_state, build_name_prompt_keyboard

@router.message(Command("branch_create"))
async def cmd_branch_create(message: Message, telegram_queue: TelegramQueue):
    """Create a new worktree branch with isolated Claude session."""
    if not await require_forum_group(message, telegram_queue):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not registered. Use /start first.")
        return

    # Check git repo
    if not is_git_repo(Path(project.cwd)):
        await telegram_queue.reply(message, "`[x]` Git repository required for /branch_create")
        return

    # Parse name argument
    args = message.text.split(maxsplit=1)
    branch_name = args[1] if len(args) > 1 else None

    # No name provided - show prompt
    if not branch_name:
        _flow_state[message.chat.id] = {
            "state": "awaiting_branch_name",
            "thread_id": message.message_thread_id,
        }
        await telegram_queue.reply(
            message,
            "Branch name?\n\nSend name or pick random",
            reply_markup=build_name_prompt_keyboard("branch"),
        )
        return

    # Rest of the function unchanged - validate and create
    await _do_branch_create_flow(message, telegram_queue, project, branch_name)
```

Also extract the validation/creation logic to a helper:

```python
async def _do_branch_create_flow(
    message: Message,
    telegram_queue: TelegramQueue,
    project,
    branch_name: str,
):
    """Validate branch name and proceed with creation flow."""
    # Sanitize branch name
    branch_name = sanitize_branch_name(branch_name)

    if not branch_name:
        await telegram_queue.reply(message, "`[x]` Invalid name")
        return

    # Check length
    max_len = max_branch_name_length(project.project_name)
    if len(branch_name) > max_len:
        await telegram_queue.reply(message, f"`[x]` Name too long (max {max_len} chars for this project)")
        return

    # Check if branch already exists
    if branch_exists(Path(project.cwd), branch_name):
        await telegram_queue.reply(message, f"`[x]` Branch `{branch_name}` already exists")
        return

    # Check if worktree directory already exists
    main_repo = Path(project.cwd)
    worktree_dir = main_repo.parent / f"{main_repo.name}-{branch_name}"
    if worktree_dir.exists():
        await telegram_queue.reply(message, f"`[x]` Directory already exists: `{worktree_dir}`")
        return

    # Get default branch
    default_branch = get_default_branch(Path(project.cwd))

    # Check if creating from worktree topic or main
    current_thread = project.threads.get(message.message_thread_id)
    if current_thread and current_thread.worktree_path:
        # From worktree topic - show base branch selection
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"From {default_branch}", callback_data=f"bc_base:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text=f"From {current_thread.name}", callback_data=f"bc_base:{branch_name}:{current_thread.name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await telegram_queue.reply(message, "Create branch from:", reply_markup=keyboard)
        return

    # From main - check uncommitted changes
    if has_uncommitted_changes(Path(project.cwd)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create clean (from last commit)", callback_data=f"bc_create:{branch_name}:{default_branch}")],
            [InlineKeyboardButton(text="Commit first", callback_data=f"bc_commit:{branch_name}")],
            [InlineKeyboardButton(text="[<<] Go back", callback_data="cancel")]
        ])
        await telegram_queue.reply(message, "`[!]` Uncommitted changes detected", reply_markup=keyboard)
        return

    # No uncommitted changes - create directly
    await do_branch_create(message.bot, message.chat.id, project, branch_name, default_branch)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_branch_name_prompt.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/branches.py tests/test_branch_name_prompt.py
git commit -m "feat(branch): show name prompt when no argument"
```

---

### Task 4: Add magic_name:branch callback

**Files:**
- Modify: `src/codogram/handlers/branches.py`
- Modify: `tests/test_branch_name_prompt.py`

**Step 1: Write the failing test**

Add to `tests/test_branch_name_prompt.py`:

```python
@pytest.fixture
def mock_callback():
    cb = MagicMock(spec=CallbackQuery)
    cb.message = MagicMock(spec=Message)
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = -100123
    cb.message.message_thread_id = None
    cb.data = "magic_name:branch"
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


@pytest.mark.asyncio
async def test_magic_name_branch_creates_with_random_name(mock_callback):
    """Magic name button generates random name and creates branch."""
    from codogram.handlers.branches import on_magic_name_branch
    from codogram.handlers.common import _flow_state

    _flow_state[-100123] = {"state": "awaiting_branch_name", "thread_id": None}

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
         patch("codogram.handlers.branches.do_branch_create") as mock_create, \
         patch("codogram.handlers.branches.get_random_magic_name", return_value="arcane"), \
         patch("pathlib.Path.exists", return_value=False):
        mock_pm.get_by_chat.return_value = mock_project

        await on_magic_name_branch(mock_callback, mock_queue)

        # Should clear flow state
        assert -100123 not in _flow_state

        # Should delete prompt message
        mock_queue.delete.assert_called_once()

        # Should create branch with magic name
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][3] == "arcane"  # branch_name argument
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_branch_name_prompt.py::test_magic_name_branch_creates_with_random_name -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

Add to `src/codogram/handlers/branches.py`:

```python
@router.callback_query(F.data == "magic_name:branch")
async def on_magic_name_branch(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle magic name button for branch creation."""
    chat_id = callback.message.chat.id

    # Clear flow state
    state = _flow_state.pop(chat_id, None)
    thread_id = state.get("thread_id") if state else callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    # Generate magic name
    existing_names = {t.name for t in project.threads.values()}
    branch_name = get_random_magic_name(existing_names)

    # Delete prompt message
    await telegram_queue.delete(callback.message)

    # Create a fake message for the flow
    fake_message = callback.message
    fake_message.message_thread_id = thread_id

    # Run creation flow
    await _do_branch_create_flow(fake_message, telegram_queue, project, branch_name)

    await callback.answer()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_branch_name_prompt.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/branches.py tests/test_branch_name_prompt.py
git commit -m "feat(branch): add magic_name callback handler"
```

---

### Task 5: Update /thread to show name prompt

**Files:**
- Modify: `src/codogram/handlers/threads.py`
- Test: `tests/test_thread_name_prompt.py` (new)

**Step 1: Write the failing test**

Create `tests/test_thread_name_prompt.py`:

```python
"""Tests for /thread name prompt flow."""
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
    msg.text = "/thread"  # No argument
    return msg


@pytest.mark.asyncio
async def test_thread_without_arg_shows_name_prompt(mock_message):
    """'/thread' without argument shows name prompt."""
    from codogram.handlers.threads import cmd_thread_create
    from codogram.handlers.common import _flow_state

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.threads = {}

    with patch("codogram.handlers.threads.project_manager") as mock_pm:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_thread_create(mock_message, mock_queue)

        # Should show prompt
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Thread name?" in call_args[0][1]

        # Should set flow state
        assert _flow_state[-100123]["state"] == "awaiting_thread_name"

    # Cleanup
    _flow_state.pop(-100123, None)


@pytest.mark.asyncio
async def test_thread_with_arg_creates_directly(mock_message):
    """'/thread mystic' skips prompt (may show confirmation for non-worktree)."""
    from codogram.handlers.threads import cmd_thread_create
    from codogram.handlers.common import _flow_state

    mock_message.text = "/thread mystic"
    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.threads = {}

    with patch("codogram.handlers.threads.project_manager") as mock_pm, \
         patch("codogram.handlers.threads.create_thread_with_session") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project
        mock_create.return_value = MagicMock()

        await cmd_thread_create(mock_message, mock_queue)

        # Should NOT set awaiting_thread_name state
        state = _flow_state.get(-100123, {})
        assert state.get("state") != "awaiting_thread_name"

        # Should call create_thread_with_session
        mock_create.assert_called_once()

    # Cleanup
    _flow_state.pop(-100123, None)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_thread_name_prompt.py -v`
Expected: FAIL (current code auto-generates name)

**Step 3: Update threads.py**

In `src/codogram/handlers/threads.py`:

```python
from .common import _flow_state, build_name_prompt_keyboard

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

    # Parse optional name from command
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        name = args[1].strip().lower()
    else:
        # No name - show prompt
        _flow_state[chat_id] = {
            "state": "awaiting_thread_name",
            "thread_id": message.message_thread_id,
        }
        await telegram_queue.reply(
            message,
            "Thread name?\n\nSend name or pick random",
            reply_markup=build_name_prompt_keyboard("thread"),
        )
        return

    # Has name - proceed with creation flow
    await _do_thread_create_flow(message, telegram_queue, project, name)
```

Add helper function:

```python
async def _do_thread_create_flow(
    message: Message,
    telegram_queue: TelegramQueue,
    project,
    name: str,
):
    """Validate and create thread with given name."""
    # Check if any non-worktree threads exist (excluding main)
    non_worktree_threads = [
        t for t in project.threads.values()
        if t.thread_id is not None and not t.worktree_path
    ]

    if non_worktree_threads:
        # Store pending thread name for confirmation
        _flow_state[message.chat.id] = {
            "state": "thread_create_pending",
            "name": name,
        }
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Create in main repo", callback_data="thread_create_confirm")],
            [InlineKeyboardButton(text="Use /branch_create instead", callback_data="branch_create_redirect")],
            [InlineKeyboardButton(text="Cancel", callback_data="cancel")]
        ])
        await telegram_queue.reply(
            message,
            "Non-worktree threads exist. For isolated work, consider /branch_create.\n"
            "Create thread in main repo anyway?",
            reply_markup=keyboard
        )
        return

    # Create directly
    thread = await create_thread_with_session(
        bot=message.bot,
        chat_id=message.chat.id,
        project=project,
        name=name,
    )

    if not thread:
        await telegram_queue.reply(message, "Error creating topic")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_thread_name_prompt.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/threads.py tests/test_thread_name_prompt.py
git commit -m "feat(thread): show name prompt when no argument"
```

---

### Task 6: Add magic_name:thread callback

**Files:**
- Modify: `src/codogram/handlers/threads.py`
- Modify: `tests/test_thread_name_prompt.py`

**Step 1: Write the failing test**

Add to `tests/test_thread_name_prompt.py`:

```python
from aiogram.types import CallbackQuery


@pytest.fixture
def mock_callback():
    cb = MagicMock(spec=CallbackQuery)
    cb.message = MagicMock(spec=Message)
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = -100123
    cb.message.message_thread_id = None
    cb.data = "magic_name:thread"
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


@pytest.mark.asyncio
async def test_magic_name_thread_creates_with_random_name(mock_callback):
    """Magic name button generates random name and creates thread."""
    from codogram.handlers.threads import on_magic_name_thread
    from codogram.handlers.common import _flow_state

    _flow_state[-100123] = {"state": "awaiting_thread_name", "thread_id": None}

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.threads = {}

    with patch("codogram.handlers.threads.project_manager") as mock_pm, \
         patch("codogram.handlers.threads.create_thread_with_session") as mock_create, \
         patch("codogram.handlers.threads.get_random_magic_name", return_value="mystic"):
        mock_pm.get_by_chat.return_value = mock_project
        mock_create.return_value = MagicMock()

        await on_magic_name_thread(mock_callback, mock_queue)

        # Should clear flow state
        assert -100123 not in _flow_state

        # Should delete prompt message
        mock_queue.delete.assert_called_once()

        # Should create thread with magic name
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["name"] == "mystic"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_thread_name_prompt.py::test_magic_name_thread_creates_with_random_name -v`
Expected: FAIL with ImportError

**Step 3: Write implementation**

Add to `src/codogram/handlers/threads.py`:

```python
@router.callback_query(F.data == "magic_name:thread")
async def on_magic_name_thread(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle magic name button for thread creation."""
    chat_id = callback.message.chat.id

    # Clear flow state
    state = _flow_state.pop(chat_id, None)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    # Generate magic name
    existing_names = {t.name for t in project.threads.values()}
    name = get_random_magic_name(existing_names)

    # Delete prompt message
    await telegram_queue.delete(callback.message)

    # Create thread (no confirmation needed for magic name - user chose random)
    thread = await create_thread_with_session(
        bot=callback.bot,
        chat_id=chat_id,
        project=project,
        name=name,
    )

    if not thread:
        await telegram_queue.send(chat_id, "Error creating topic")

    await callback.answer()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_thread_name_prompt.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/threads.py tests/test_thread_name_prompt.py
git commit -m "feat(thread): add magic_name callback handler"
```

---

### Task 7: Handle text input as name in messages.py

**Files:**
- Modify: `src/codogram/handlers/messages.py`
- Test: `tests/test_name_input_handler.py` (new)

**Step 1: Write the failing test**

Create `tests/test_name_input_handler.py`:

```python
"""Tests for handling text input as branch/thread name."""
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
async def test_text_as_branch_name(mock_message):
    """Text message used as branch name when awaiting."""
    from codogram.handlers.messages import on_message
    from codogram.handlers.common import _flow_state

    _flow_state[-100123] = {"state": "awaiting_branch_name", "thread_id": None}

    mock_queue = AsyncMock()
    mock_project = MagicMock()
    mock_project.cwd = "/tmp/test"
    mock_project.project_name = "test"
    mock_project.threads = {}

    with patch("codogram.handlers.messages.project_manager") as mock_pm, \
         patch("codogram.handlers.messages.handle_branch_name_input") as mock_handler:
        mock_pm.get_by_chat.return_value = mock_project

        await on_message(mock_message, mock_queue)

        # Should call branch name handler
        mock_handler.assert_called_once()

        # Should clear state
        assert -100123 not in _flow_state


@pytest.mark.asyncio
async def test_text_as_thread_name(mock_message):
    """Text message used as thread name when awaiting."""
    from codogram.handlers.messages import on_message
    from codogram.handlers.common import _flow_state

    _flow_state[-100123] = {"state": "awaiting_thread_name", "thread_id": None}

    mock_queue = AsyncMock()

    with patch("codogram.handlers.messages.handle_thread_name_input") as mock_handler:
        await on_message(mock_message, mock_queue)

        mock_handler.assert_called_once()
        assert -100123 not in _flow_state


@pytest.mark.asyncio
async def test_regular_message_not_intercepted(mock_message):
    """Regular message goes to tmux when no awaiting state."""
    from codogram.handlers.messages import on_message
    from codogram.handlers.common import _flow_state

    # No flow state
    _flow_state.pop(-100123, None)

    mock_queue = AsyncMock()

    with patch("codogram.handlers.messages._message_router") as mock_router:
        mock_router.route.return_value = MagicMock(action="NO_PROJECT")

        await on_message(mock_message, mock_queue)

        # Should route normally
        mock_router.route.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_name_input_handler.py -v`
Expected: FAIL (no interception logic exists)

**Step 3: Write implementation**

Modify `src/codogram/handlers/messages.py`:

```python
from .common import _flow_state, NAME_FLOW_STATES

@router.message()
async def on_message(message: Message, telegram_queue: TelegramQueue):
    """Route regular messages to tmux sessions."""
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

    # Check if awaiting name input
    state = _flow_state.get(chat_id)
    if state and state.get("state") in NAME_FLOW_STATES:
        await _handle_name_input(message, telegram_queue, state)
        return

    # Normal routing...
    thread_id = message.message_thread_id
    result = _message_router.route(chat_id, thread_id, text)
    # ... rest unchanged


async def _handle_name_input(message: Message, telegram_queue: TelegramQueue, state: dict):
    """Handle text message as branch/thread name."""
    from .branches import _do_branch_create_flow
    from .threads import _do_thread_create_flow
    from ..session_manager import project_manager
    from ..git_utils import sanitize_branch_name

    chat_id = message.chat.id
    state_type = state.get("state")
    name = message.text.strip()

    # Clear state
    _flow_state.pop(chat_id, None)

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "`[!]` Project not found")
        return

    if state_type == "awaiting_branch_name":
        await _do_branch_create_flow(message, telegram_queue, project, name)
    elif state_type == "awaiting_thread_name":
        # Sanitize for thread too
        name = sanitize_branch_name(name)
        if not name:
            await telegram_queue.reply(message, "`[x]` Invalid name")
            return
        await _do_thread_create_flow(message, telegram_queue, project, name)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_name_input_handler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/messages.py tests/test_name_input_handler.py
git commit -m "feat(messages): intercept text as branch/thread name"
```

---

### Task 8: Run all tests and verify

**Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

**Step 2: Fix any failures**

If tests fail, fix issues and re-run.

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: test suite fixes"
```

---

### Task 9: Manual E2E test

**Reference:** `docs/e2e/CLAUDE.md`

**Step 1: Ask user for test chat ID**

**Step 2: Restart bot**

```bash
./restart.sh
```

**Step 3: Test /branch without argument**

```
send_message(chat_id, "/branch")
# Expect: "Branch name?" with buttons
```

**Step 4: Test magic name button**

```
press_inline_button(chat_id, button_text="🔮 Magic name")
# Expect: Branch created with random name
```

**Step 5: Test /thread without argument**

```
send_message(chat_id, "/thread")
# Expect: "Thread name?" with buttons
```

**Step 6: Test text name input**

```
send_message(chat_id, "/branch")
send_message(chat_id, "test-feature")
# Expect: Branch created with name "test-feature"
```

---

### Task 10: Update docs and commit

**Files:**
- Modify: `docs/ROADMAP.md` - move "Thread create UX" to Done
- Move: `docs/designs/2026-01-07-thread-branch-create-ux.md` → `docs/designs/done/`

**Step 1: Update ROADMAP.md**

Move the "Thread create UX" section from Backlog to Done with description of what was implemented.

**Step 2: Move design to done**

```bash
mv docs/designs/2026-01-07-thread-branch-create-ux.md docs/designs/done/
```

**Step 3: Commit**

```bash
git add docs/
git commit -m "docs: mark thread/branch create UX as done"
```
