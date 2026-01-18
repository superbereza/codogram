# Start Flow v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement intuitive onboarding flow triggered when bot is added to chat, with three setup paths: Clone/Connect/New.

**Architecture:** Modular handlers in `handlers/setup/`, services in `services/setup/`, keyboards in `keyboards/setup/`. FSM-based flow with `SetupFlow` states. Middleware blocks non-setup commands during setup.

**Tech Stack:** aiogram 3.x, FSM, inline keyboards, asyncio

**Design Document:** `docs/designs/2026-01-18-start-flow-v2.md`

---

## Phase 1: Infrastructure

### Task 1: Add SetupFlow FSM States

**Files:**
- Modify: `src/codogram/domain/states.py`
- Test: `tests/test_states.py` (new)

**Step 1: Write the failing test**

```python
# tests/test_states.py
from codogram.domain.states import SetupFlow


def test_setup_flow_has_all_states():
    """SetupFlow has all required states."""
    assert hasattr(SetupFlow, 'awaiting_admin_rights')
    assert hasattr(SetupFlow, 'awaiting_setup_type')
    assert hasattr(SetupFlow, 'awaiting_clone_url')
    assert hasattr(SetupFlow, 'awaiting_folder_select')
    assert hasattr(SetupFlow, 'viewing_connected_projects')
    assert hasattr(SetupFlow, 'awaiting_project_name')
    assert hasattr(SetupFlow, 'awaiting_git_choice')
    assert hasattr(SetupFlow, 'awaiting_rename_confirm')
    assert hasattr(SetupFlow, 'launching')
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_states.py -v`
Expected: FAIL with "AttributeError: type object 'SetupFlow' has no attribute..."

**Step 3: Write minimal implementation**

Add to `src/codogram/domain/states.py`:

```python
class SetupFlow(StatesGroup):
    """States for new onboarding flow (v2).

    See docs/designs/2026-01-18-start-flow-v2.md for flow diagrams.
    """
    awaiting_admin_rights = State()
    awaiting_setup_type = State()        # Clone/Connect/New
    awaiting_clone_url = State()
    awaiting_folder_select = State()     # pagination in callback_data
    viewing_connected_projects = State()
    awaiting_project_name = State()
    awaiting_git_choice = State()
    awaiting_rename_confirm = State()
    launching = State()                   # Blocking state during launch
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_states.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/domain/states.py tests/test_states.py
git commit -m "feat(setup): add SetupFlow FSM states"
```

---

### Task 2: Add SETUP_COMMANDS to Menu Service

**Files:**
- Modify: `src/codogram/services/menu.py`
- Test: `tests/test_menu_service.py`

**Step 1: Write the failing test**

Add to `tests/test_menu_service.py`:

```python
from codogram.services.menu import SETUP_COMMANDS


def test_setup_commands_count():
    """Setup menu has 4 commands."""
    assert len(SETUP_COMMANDS) == 4


def test_setup_commands_list():
    """Setup commands are start, reset_all, help, get_debug_ids."""
    commands = [c.command for c in SETUP_COMMANDS]
    assert commands == ["start", "reset_all", "help", "get_debug_ids"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_menu_service.py::test_setup_commands_count -v`
Expected: FAIL with "cannot import name 'SETUP_COMMANDS'"

**Step 3: Write minimal implementation**

Add to `src/codogram/services/menu.py` after `FORUM_COMMANDS`:

```python
# Setup commands (during onboarding)
SETUP_COMMANDS = [
    BotCommand(command="start", description="Restart setup"),
    BotCommand(command="reset_all", description="Cancel setup"),
    BotCommand(command="help", description="Get help"),
    BotCommand(command="get_debug_ids", description="Show debug IDs"),
]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_menu_service.py -v`
Expected: PASS (all menu tests)

**Step 5: Commit**

```bash
git add src/codogram/services/menu.py tests/test_menu_service.py
git commit -m "feat(setup): add SETUP_COMMANDS to menu service"
```

---

### Task 3: Add Setup Strings

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add setup strings**

Add to `src/codogram/strings.py`:

```python
# --- Setup Flow v2 ---

# Base directory
SETUP_BASE_DIR_MISSING = f"""{STATUS_ERR} Configure base directory first

Set BASE_DIR in \\.env file:
`BASE_DIR=/home/user/dev`

Then restart the bot\\."""

# Admin rights
SETUP_ADMIN_REQUIRED = f"""{STATUS_WARN} Grant admin rights to continue

Bot needs admin rights to:
• Rename chat to match project
• Manage topics for branches

Open chat settings → Administrators → Add bot as admin"""

SETUP_ADMIN_CHECK_FAILED = f"{STATUS_WARN} Still missing admin rights"

# Chat type errors
SETUP_PRIVATE_CHAT = f"{STATUS_ERR} Add bot to a group chat"
SETUP_CHANNEL_NOT_SUPPORTED = f"{STATUS_ERR} Channels not supported"
SETUP_ALREADY_IN_PROGRESS = f"{STATUS_INFO} Setup already in progress"

# Setup type selection
SETUP_CHOOSE_TYPE = "How would you like to set up this project?"

# Clone flow
SETUP_CLONE_URL_PROMPT = """Send repository URL:
• SSH: `git@github.com:user/repo.git`
• HTTPS: `https://github.com/user/repo.git`"""

SETUP_CLONE_PROGRESS = f"{STATUS_PENDING} Cloning repository..."
SETUP_CLONE_FAILED = f"{STATUS_ERR} Clone failed: {{error}}"
SETUP_CLONE_SSH_HINT = "SSH key may not be configured. Try HTTPS URL instead."
SETUP_CLONE_AUTH_HINT = "Repository may be private. Check authentication."

# Folder selection
SETUP_FOLDER_SELECT = "Select folder to connect:"
SETUP_FOLDER_EMPTY = f"{STATUS_WARN} No folders found in `{{base_dir}}`"
SETUP_FOLDER_ALL_CONNECTED = f"""{STATUS_INFO} All folders are already connected

Start a new project instead?"""
SETUP_FOLDER_NOT_FOUND = f"{STATUS_ERR} Folder `{{name}}` not found"
SETUP_FOLDER_USE_BUTTONS = "Select a folder from the list above\\nor use \\[<< Go back\\] to return\\."

# View connected
SETUP_CONNECTED_HEADER = "Connected projects:"
SETUP_CONNECTED_EMPTY = "No projects connected yet"
SETUP_CONNECTED_TAP_HINT = "Tap chat name to open\\."
SETUP_CONNECTED_NO_LINK = "(no link)"

# New project
SETUP_PROJECT_NAME_PROMPT = """Project folder name?

Suggested: `{suggested}`

Or send custom name"""

SETUP_PROJECT_NAME_INVALID = f"{STATUS_ERR} Invalid name\\. Use letters, digits, \\- and \\_ only"
SETUP_PROJECT_EXISTS = f"""{STATUS_WARN} Folder `{{name}}` already exists

What to do?"""

# Git choice
SETUP_GIT_CHOICE = "Git setup for `{folder}`?"
SETUP_GIT_GH_NOT_INSTALLED = f"{STATUS_ERR} `gh` CLI not installed\\. Install from https://cli\\.github\\.com"
SETUP_GIT_GH_NOT_AUTH = f"{STATUS_ERR} `gh` not authenticated\\. Run `gh auth login` first"

# Rename
SETUP_RENAME_PROMPT = "Rename chat to `{name}`?"
SETUP_RENAME_FAILED = f"{STATUS_WARN} Couldn't rename chat \\(missing permissions?\\)\\nContinuing with project setup\\.\\.\\."

# Launch
SETUP_LAUNCH_PROGRESS = f"{STATUS_PENDING} Setting up project..."
SETUP_LAUNCH_MKDIR_FAILED = f"{STATUS_ERR} Failed to create directory: {{error}}"
SETUP_LAUNCH_SUCCESS = f"""{STATUS_OK} Project `{{project}}` ready

Commands available:
• /esc — cancel operation
• /clear — clear context
• /auto_accept — toggle auto\\-accept
• /thread — new topic

Terminal: `tmux attach \\-t {{tmux_name}}`"""

# Buttons
BTN_CLONE = "Clone repository"
BTN_CONNECT = "Connect to existing folder"
BTN_NEW = "Start new project"
BTN_CHECK_RIGHTS = "Check rights"
BTN_GO_BACK = "<< Go back"
BTN_BACK_TO_FOLDERS = "<< Back to folders"
BTN_VIEW_CONNECTED = "View connected projects"
BTN_RENAME_YES = "Yes, rename"
BTN_RENAME_NO = "No"
BTN_GIT_INIT = "git init"
BTN_GIT_GH = "git init + gh repo create"
BTN_GIT_CLONE = "git clone"
BTN_GIT_NONE = "No git"
BTN_RETRY = "Retry"
BTN_USE_EXISTING = "Use existing"
BTN_DIFFERENT_NAME = "Different name"
```

**Step 2: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat(setup): add setup flow v2 strings"
```

---

### Task 4: Create Setup Keyboards Directory

**Files:**
- Create: `src/codogram/keyboards/setup/__init__.py`
- Create: `src/codogram/keyboards/setup/setup_type.py`
- Test: `tests/keyboards/test_setup_type.py`

**Step 1: Create directory and __init__.py**

```bash
mkdir -p src/codogram/keyboards/setup
```

**Step 2: Write the failing test**

```python
# tests/keyboards/test_setup_type.py
from codogram.keyboards.setup.setup_type import (
    setup_type_keyboard,
    admin_check_keyboard,
)


def test_setup_type_keyboard_has_three_buttons():
    """Setup type keyboard has Clone/Connect/New buttons."""
    kb = setup_type_keyboard()
    # Flatten all buttons
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 3

    texts = [btn.text for btn in buttons]
    assert "Clone repository" in texts
    assert "Connect to existing folder" in texts
    assert "Start new project" in texts


def test_setup_type_keyboard_callback_data():
    """Setup type buttons have correct callback_data."""
    kb = setup_type_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]

    callbacks = [btn.callback_data for btn in buttons]
    assert "setup:clone" in callbacks
    assert "setup:connect" in callbacks
    assert "setup:new" in callbacks


def test_admin_check_keyboard():
    """Admin check keyboard has Check rights button."""
    kb = admin_check_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]

    assert len(buttons) == 1
    assert buttons[0].text == "Check rights"
    assert buttons[0].callback_data == "admin:check"
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/keyboards/test_setup_type.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 4: Write implementation**

```python
# src/codogram/keyboards/setup/__init__.py
"""Setup flow keyboards."""
from .setup_type import admin_check_keyboard, setup_type_keyboard

__all__ = ["setup_type_keyboard", "admin_check_keyboard"]
```

```python
# src/codogram/keyboards/setup/setup_type.py
"""Setup type selection keyboards."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings


def setup_type_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for setup type selection (Clone/Connect/New)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_CLONE, callback_data="setup:clone")],
        [InlineKeyboardButton(text=strings.BTN_CONNECT, callback_data="setup:connect")],
        [InlineKeyboardButton(text=strings.BTN_NEW, callback_data="setup:new")],
    ])


def admin_check_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with Check rights button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_CHECK_RIGHTS, callback_data="admin:check")],
    ])
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/keyboards/test_setup_type.py -v`
Expected: PASS

**Step 6: Commit**

```bash
mkdir -p tests/keyboards
touch tests/keyboards/__init__.py
git add src/codogram/keyboards/setup/ tests/keyboards/
git commit -m "feat(setup): add setup type keyboards"
```

---

### Task 5: Create Setup Services Directory Structure

**Files:**
- Create: `src/codogram/services/setup/__init__.py`
- Create: `src/codogram/services/setup/admin_rights.py`
- Test: `tests/services/test_admin_rights.py`

**Step 1: Write the failing test**

```python
# tests/services/test_admin_rights.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from codogram.services.setup.admin_rights import check_bot_admin_rights


@pytest.mark.asyncio
async def test_check_admin_rights_returns_true_when_admin():
    """Returns True when bot has can_change_info right."""
    bot = AsyncMock()
    bot.id = 123456

    member = MagicMock()
    member.status = "administrator"
    member.can_change_info = True

    bot.get_chat_member.return_value = member

    result = await check_bot_admin_rights(bot, chat_id=-1001234567890)
    assert result is True


@pytest.mark.asyncio
async def test_check_admin_rights_returns_false_when_not_admin():
    """Returns False when bot is just a member."""
    bot = AsyncMock()
    bot.id = 123456

    member = MagicMock()
    member.status = "member"

    bot.get_chat_member.return_value = member

    result = await check_bot_admin_rights(bot, chat_id=-1001234567890)
    assert result is False


@pytest.mark.asyncio
async def test_check_admin_rights_returns_false_without_can_change_info():
    """Returns False when admin but no can_change_info."""
    bot = AsyncMock()
    bot.id = 123456

    member = MagicMock()
    member.status = "administrator"
    member.can_change_info = False

    bot.get_chat_member.return_value = member

    result = await check_bot_admin_rights(bot, chat_id=-1001234567890)
    assert result is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_admin_rights.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/codogram/services/setup/__init__.py
"""Setup flow services."""
from .admin_rights import check_bot_admin_rights

__all__ = ["check_bot_admin_rights"]
```

```python
# src/codogram/services/setup/admin_rights.py
"""Admin rights checking service."""
import logging

from aiogram import Bot

logger = logging.getLogger(__name__)


async def check_bot_admin_rights(bot: Bot, chat_id: int) -> bool:
    """Check if bot has required admin rights (can_change_info).

    Args:
        bot: Bot instance
        chat_id: Chat to check

    Returns:
        True if bot has can_change_info right, False otherwise
    """
    try:
        member = await bot.get_chat_member(chat_id, bot.id)

        if member.status not in ("administrator", "creator"):
            return False

        # Check for can_change_info right
        if hasattr(member, 'can_change_info') and not member.can_change_info:
            return False

        return True

    except Exception as e:
        logger.warning(f"Failed to check admin rights for chat {chat_id}: {e}")
        return False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_admin_rights.py -v`
Expected: PASS

**Step 5: Commit**

```bash
mkdir -p src/codogram/services/setup tests/services
touch tests/services/__init__.py
git add src/codogram/services/setup/ tests/services/
git commit -m "feat(setup): add admin rights checking service"
```

---

### Task 6: Create Setup Handlers Directory Structure

**Files:**
- Create: `src/codogram/handlers/setup/__init__.py`
- Create: `src/codogram/handlers/setup/triggers.py`

**Step 1: Create directory structure**

```bash
mkdir -p src/codogram/handlers/setup
```

**Step 2: Write __init__.py with router**

```python
# src/codogram/handlers/setup/__init__.py
"""Setup flow handlers.

This module provides the new onboarding flow (v2) that triggers when:
1. Bot is added to a chat
2. /start in a chat without project
3. Any message in a chat without project

See docs/designs/2026-01-18-start-flow-v2.md for flow diagrams.
"""
from aiogram import Router

setup_router = Router(name="setup")

# Import routers after setup_router is defined to avoid circular imports
from . import triggers  # noqa: E402, F401

# Include sub-routers
setup_router.include_router(triggers.router)
```

**Step 3: Write triggers.py with my_chat_member handler**

```python
# src/codogram/handlers/setup/triggers.py
"""Setup flow trigger handlers.

Entry points:
- my_chat_member: bot added to chat or granted admin
- /start in unregistered chat
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated

from ...domain.states import SetupFlow
from ...services.setup import check_bot_admin_rights
from ...keyboards.setup import admin_check_keyboard, setup_type_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_triggers")


def _is_group_chat(chat_type: str) -> bool:
    """Check if chat type is a group (not private/channel)."""
    return chat_type in ("group", "supergroup")


@router.my_chat_member(
    F.new_chat_member.status.in_({"member", "administrator"})
)
async def on_bot_added(event: ChatMemberUpdated, state: FSMContext):
    """Handle bot being added to chat or granted admin rights.

    Triggers setup flow for new chats.
    """
    chat = event.chat

    # Block private chats
    if chat.type == "private":
        await event.answer(strings.SETUP_PRIVATE_CHAT)
        return

    # Block channels
    if chat.type == "channel":
        await event.answer(strings.SETUP_CHANNEL_NOT_SUPPORTED)
        return

    # Check if setup already in progress
    current_state = await state.get_state()
    if current_state and current_state.startswith("SetupFlow:"):
        logger.debug(f"Setup already in progress for chat {chat.id}")
        return

    # TODO: Check if project already registered for this chat
    # For now, always start setup

    await _start_setup_flow(event, state)


async def _start_setup_flow(event: ChatMemberUpdated, state: FSMContext):
    """Start the setup flow - check admin rights first."""
    chat = event.chat
    bot = event.bot

    # Check admin rights
    has_rights = await check_bot_admin_rights(bot, chat.id)

    if not has_rights:
        # Ask for admin rights
        await state.set_state(SetupFlow.awaiting_admin_rights)
        await bot.send_message(
            chat.id,
            strings.SETUP_ADMIN_REQUIRED,
            reply_markup=admin_check_keyboard(),
        )
        return

    # Has rights - show setup type selection
    await state.set_state(SetupFlow.awaiting_setup_type)
    await bot.send_message(
        chat.id,
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/setup/
git commit -m "feat(setup): add setup handlers with my_chat_member trigger"
```

---

### Task 7: Register Setup Router in Main

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Add import and include router**

Find the router registration section in `main.py` and add:

```python
from .handlers.setup import setup_router

# In the setup_routers() or similar function, add:
dp.include_router(setup_router)
```

Note: The setup_router should be included BEFORE the start.py router to handle my_chat_member events first.

**Step 2: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(setup): register setup router in main"
```

---

## Phase 2: Admin Check Flow

### Task 8: Add Admin Check Callback Handler

**Files:**
- Create: `src/codogram/handlers/setup/admin_check.py`
- Test: Manual E2E test

**Step 1: Write implementation**

```python
# src/codogram/handlers/setup/admin_check.py
"""Admin rights check handlers."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...domain.states import SetupFlow
from ...services.setup import check_bot_admin_rights
from ...keyboards.setup import admin_check_keyboard, setup_type_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_admin_check")


@router.callback_query(
    SetupFlow.awaiting_admin_rights,
    F.data == "admin:check"
)
async def on_check_rights(callback: CallbackQuery, state: FSMContext):
    """Handle Check rights button press."""
    await callback.answer()  # Acknowledge callback

    chat_id = callback.message.chat.id
    bot = callback.bot

    has_rights = await check_bot_admin_rights(bot, chat_id)

    if has_rights:
        # Proceed to setup type selection
        await state.set_state(SetupFlow.awaiting_setup_type)
        await callback.message.edit_text(
            strings.SETUP_CHOOSE_TYPE,
            reply_markup=setup_type_keyboard(),
        )
    else:
        # Still no rights - show message again
        await callback.message.edit_text(
            strings.SETUP_ADMIN_REQUIRED + f"\n\n{strings.SETUP_ADMIN_CHECK_FAILED}",
            reply_markup=admin_check_keyboard(),
        )


@router.my_chat_member(
    SetupFlow.awaiting_admin_rights,
    F.new_chat_member.status == "administrator"
)
async def on_admin_granted(event: ChatMemberUpdated, state: FSMContext):
    """Handle bot being granted admin rights while waiting."""
    chat = event.chat
    bot = event.bot

    # Verify the rights
    has_rights = await check_bot_admin_rights(bot, chat.id)

    if has_rights:
        await state.set_state(SetupFlow.awaiting_setup_type)
        await bot.send_message(
            chat.id,
            strings.SETUP_CHOOSE_TYPE,
            reply_markup=setup_type_keyboard(),
        )
```

**Step 2: Update __init__.py to include router**

```python
# src/codogram/handlers/setup/__init__.py
from . import admin_check  # noqa: E402, F401
setup_router.include_router(admin_check.router)
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/setup/admin_check.py src/codogram/handlers/setup/__init__.py
git commit -m "feat(setup): add admin check callback handler"
```

---

## Phase 3: Setup Type Selection

### Task 9: Add Setup Type Callback Handler

**Files:**
- Create: `src/codogram/handlers/setup/setup_type.py`

**Step 1: Write implementation**

```python
# src/codogram/handlers/setup/setup_type.py
"""Setup type selection handlers (Clone/Connect/New)."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...domain.states import SetupFlow
from ...keyboards.setup import setup_type_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_type")


@router.callback_query(
    SetupFlow.awaiting_setup_type,
    F.data == "setup:clone"
)
async def on_clone_selected(callback: CallbackQuery, state: FSMContext):
    """Handle Clone repository selection."""
    await callback.answer()

    await state.set_state(SetupFlow.awaiting_clone_url)
    await state.update_data(setup_type="clone")

    # Import here to avoid circular imports
    from ...keyboards.setup.common import go_back_keyboard

    await callback.message.edit_text(
        strings.SETUP_CLONE_URL_PROMPT,
        reply_markup=go_back_keyboard("clone:back"),
    )


@router.callback_query(
    SetupFlow.awaiting_setup_type,
    F.data == "setup:connect"
)
async def on_connect_selected(callback: CallbackQuery, state: FSMContext):
    """Handle Connect to existing folder selection."""
    await callback.answer()

    await state.set_state(SetupFlow.awaiting_folder_select)
    await state.update_data(setup_type="connect")

    # Import here to avoid circular imports
    from .connect_flow import show_folder_selection

    await show_folder_selection(callback.message, state, page=0)


@router.callback_query(
    SetupFlow.awaiting_setup_type,
    F.data == "setup:new"
)
async def on_new_selected(callback: CallbackQuery, state: FSMContext):
    """Handle Start new project selection."""
    await callback.answer()

    await state.set_state(SetupFlow.awaiting_project_name)
    await state.update_data(setup_type="new")

    # Import here to avoid circular imports
    from .new_project_flow import show_project_name_prompt

    await show_project_name_prompt(callback.message, state)
```

**Step 2: Create common keyboard helper**

```python
# src/codogram/keyboards/setup/common.py
"""Common keyboard helpers for setup flow."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings


def go_back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    """Create keyboard with single Go back button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data=callback_data)],
    ])
```

**Step 3: Update keyboards __init__.py**

```python
# src/codogram/keyboards/setup/__init__.py
from .common import go_back_keyboard
from .setup_type import admin_check_keyboard, setup_type_keyboard

__all__ = ["setup_type_keyboard", "admin_check_keyboard", "go_back_keyboard"]
```

**Step 4: Update handlers __init__.py**

```python
from . import setup_type  # noqa: E402, F401
setup_router.include_router(setup_type.router)
```

**Step 5: Commit**

```bash
git add src/codogram/keyboards/setup/ src/codogram/handlers/setup/
git commit -m "feat(setup): add setup type selection handler"
```

---

## Phase 4: Clone Flow

### Task 10: Add Clone Flow Handlers

**Files:**
- Create: `src/codogram/handlers/setup/clone_flow.py`
- Reuse: `src/codogram/services/start_flow.py` (git_clone function)

**Step 1: Write implementation**

```python
# src/codogram/handlers/setup/clone_flow.py
"""Clone repository flow handlers."""
import logging
import re
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...config import settings
from ...domain.states import SetupFlow
from ...domain.validators import validate_git_url
from ...keyboards.setup import go_back_keyboard, setup_type_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_clone")


def extract_project_name_from_url(url: str) -> str | None:
    """Extract project name from git URL.

    Examples:
        https://github.com/user/awesome-project.git -> awesome-project
        git@github.com:user/awesome-project.git -> awesome-project
    """
    # HTTPS format
    https_match = re.search(r'/([^/]+?)(?:\.git)?$', url)
    if https_match:
        return https_match.group(1)

    # SSH format
    ssh_match = re.search(r':([^/]+/)?([^/]+?)(?:\.git)?$', url)
    if ssh_match:
        return ssh_match.group(2)

    return None


@router.callback_query(
    SetupFlow.awaiting_clone_url,
    F.data == "clone:back"
)
async def on_clone_back(callback: CallbackQuery, state: FSMContext):
    """Handle Go back from clone URL input."""
    await callback.answer()

    await state.set_state(SetupFlow.awaiting_setup_type)
    await callback.message.edit_text(
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )


@router.message(SetupFlow.awaiting_clone_url)
async def on_clone_url(message: Message, state: FSMContext):
    """Handle clone URL input."""
    url = message.text.strip()

    # Validate URL
    validation = validate_git_url(url)
    if not validation.is_valid:
        await message.answer(
            f"{strings.STATUS_ERR} {validation.error}",
            reply_markup=go_back_keyboard("clone:back"),
        )
        return

    # Extract project name
    project_name = extract_project_name_from_url(url)
    if not project_name:
        await message.answer(
            f"{strings.STATUS_ERR} Could not extract project name from URL",
            reply_markup=go_back_keyboard("clone:back"),
        )
        return

    # Check if folder already exists
    base_dir = Path(settings.base_dir).expanduser()
    target_dir = base_dir / project_name

    if target_dir.exists():
        await state.update_data(clone_url=url, project_name=project_name)
        # TODO: Show "folder exists" dialog
        await message.answer(
            strings.SETUP_PROJECT_EXISTS.format(name=project_name),
            reply_markup=go_back_keyboard("clone:back"),
        )
        return

    # Store data and proceed to clone
    await state.update_data(
        clone_url=url,
        project_name=project_name,
        target_dir=str(target_dir),
    )

    # Perform clone
    await _do_clone(message, state)


async def _do_clone(message: Message, state: FSMContext):
    """Perform the git clone operation."""
    data = await state.get_data()
    url = data["clone_url"]
    target_dir = data["target_dir"]
    project_name = data["project_name"]

    # Show progress
    progress_msg = await message.answer(strings.SETUP_CLONE_PROGRESS)

    # Import git_clone from existing service
    from ...services.start_flow import git_clone

    result = await git_clone(url, target_dir)

    if not result.success:
        error_msg = result.error or "Unknown error"

        # Add hints for common errors
        hint = ""
        if "Permission denied" in error_msg:
            hint = f"\n\n{strings.SETUP_CLONE_SSH_HINT}"
        elif "Authentication failed" in error_msg or "401" in error_msg:
            hint = f"\n\n{strings.SETUP_CLONE_AUTH_HINT}"

        await progress_msg.edit_text(
            strings.SETUP_CLONE_FAILED.format(error=error_msg) + hint,
            reply_markup=go_back_keyboard("clone:back"),
        )
        return

    # Clone successful - check if rename needed
    chat_title = message.chat.title or ""

    if chat_title != project_name:
        await state.set_state(SetupFlow.awaiting_rename_confirm)
        await state.update_data(rename_to=project_name)

        from ...keyboards.setup.confirm import rename_confirm_keyboard
        await progress_msg.edit_text(
            strings.SETUP_RENAME_PROMPT.format(name=project_name),
            reply_markup=rename_confirm_keyboard(),
        )
    else:
        # No rename needed - proceed to launch
        await _proceed_to_launch(progress_msg, state)


async def _proceed_to_launch(message: Message, state: FSMContext):
    """Proceed to launch phase."""
    from .launch import do_launch
    await do_launch(message, state)
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/setup/clone_flow.py
git commit -m "feat(setup): add clone flow handlers"
```

---

## Phase 5: Connect Flow

### Task 11: Add SetupContext Dataclass

**Files:**
- Create: `src/codogram/domain/setup_models.py`
- Test: `tests/domain/test_setup_models.py`

**Step 1: Write the failing test**

```python
# tests/domain/test_setup_models.py
import pytest
from codogram.domain.setup_models import SetupContext


def test_setup_context_has_all_fields():
    """SetupContext has all required fields."""
    ctx = SetupContext(
        setup_type="clone",
        project_name="my-project",
    )
    assert ctx.setup_type == "clone"
    assert ctx.project_name == "my-project"
    assert ctx.clone_url is None
    assert ctx.target_dir is None
    assert ctx.rename_to is None


def test_setup_context_from_dict():
    """SetupContext can be created from dict (FSM data)."""
    data = {"setup_type": "connect", "project_name": "test"}
    ctx = SetupContext.from_dict(data)
    assert ctx.setup_type == "connect"


def test_setup_context_to_dict():
    """SetupContext can be converted to dict for FSM."""
    ctx = SetupContext(setup_type="new", project_name="foo")
    data = ctx.to_dict()
    assert data["setup_type"] == "new"
    assert data["project_name"] == "foo"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/domain/test_setup_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/codogram/domain/setup_models.py
"""Data models for setup flow."""
from dataclasses import dataclass, field, asdict
from typing import Literal


SetupType = Literal["clone", "connect", "new"]


@dataclass
class SetupContext:
    """Typed context for setup flow FSM data.

    Prevents typos in key names and provides autocomplete.
    """
    setup_type: SetupType | None = None
    project_name: str | None = None
    clone_url: str | None = None
    target_dir: str | None = None
    rename_to: str | None = None
    git_choice: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SetupContext":
        """Create from FSM data dict."""
        return cls(
            setup_type=data.get("setup_type"),
            project_name=data.get("project_name"),
            clone_url=data.get("clone_url"),
            target_dir=data.get("target_dir"),
            rename_to=data.get("rename_to"),
            git_choice=data.get("git_choice"),
        )

    def to_dict(self) -> dict:
        """Convert to dict for FSM storage."""
        return {k: v for k, v in asdict(self).items() if v is not None}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/domain/test_setup_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
mkdir -p tests/domain
touch tests/domain/__init__.py
git add src/codogram/domain/setup_models.py tests/domain/
git commit -m "feat(setup): add SetupContext dataclass for typed FSM data"
```

---

### Task 12: Add Folder List Service

**Files:**
- Create: `src/codogram/services/setup/folder_list.py`
- Test: `tests/services/test_folder_list.py`

**Step 1: Write the failing test**

```python
# tests/services/test_folder_list.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from codogram.services.setup.folder_list import (
    list_available_folders,
    get_connected_folders,
)


def test_list_available_folders_excludes_hidden(tmp_path):
    """Hidden folders are excluded."""
    (tmp_path / "visible").mkdir()
    (tmp_path / ".hidden").mkdir()

    folders = list_available_folders(tmp_path, connected=set())
    assert "visible" in folders
    assert ".hidden" not in folders


def test_list_available_folders_excludes_connected(tmp_path):
    """Already connected folders are excluded."""
    (tmp_path / "project1").mkdir()
    (tmp_path / "project2").mkdir()

    folders = list_available_folders(tmp_path, connected={"project1"})
    assert "project1" not in folders
    assert "project2" in folders


def test_list_available_folders_excludes_symlinks(tmp_path):
    """Symlinks are excluded."""
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")

    folders = list_available_folders(tmp_path, connected=set())
    assert "real" in folders
    assert "link" not in folders


def test_list_available_folders_sorted(tmp_path):
    """Folders are sorted alphabetically."""
    (tmp_path / "zebra").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()

    folders = list_available_folders(tmp_path, connected=set())
    assert folders == ["alpha", "beta", "zebra"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_folder_list.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/codogram/services/setup/folder_list.py
"""Folder listing service for connect flow."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def list_available_folders(
    base_dir: Path,
    connected: set[str],
) -> list[str]:
    """List folders available for connection.

    Args:
        base_dir: Base directory to scan
        connected: Set of folder names already connected to Codogram

    Returns:
        Sorted list of available folder names
    """
    folders = []

    try:
        for item in base_dir.iterdir():
            # Skip non-directories
            if not item.is_dir():
                continue

            # Skip hidden folders
            if item.name.startswith("."):
                continue

            # Skip symlinks
            if item.is_symlink():
                continue

            # Skip already connected
            if item.name in connected:
                continue

            folders.append(item.name)
    except PermissionError as e:
        logger.warning(f"Cannot list {base_dir}: {e}")
        return []

    return sorted(folders)


def get_connected_folders() -> dict[str, int]:
    """Get dict of folder_name -> chat_id for connected projects.

    Returns:
        Dict mapping folder names to their chat IDs
    """
    from ...session_manager import ProjectManager

    pm = ProjectManager()
    result = {}

    for project_name, project_data in pm.projects.items():
        result[project_name] = project_data.get("chat_id")

    return result
```

**Step 4: Update services/setup/__init__.py**

```python
# src/codogram/services/setup/__init__.py
from .admin_rights import check_bot_admin_rights
from .folder_list import list_available_folders, get_connected_folders

__all__ = [
    "check_bot_admin_rights",
    "list_available_folders",
    "get_connected_folders",
]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/services/test_folder_list.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/services/setup/folder_list.py tests/services/test_folder_list.py
git commit -m "feat(setup): add folder list service"
```

---

### Task 13: Add Folder Select Keyboard

**Files:**
- Create: `src/codogram/keyboards/setup/folder_select.py`
- Test: `tests/keyboards/test_folder_select.py`

**Step 1: Write the failing test**

```python
# tests/keyboards/test_folder_select.py
import pytest
from codogram.keyboards.setup.folder_select import (
    folder_select_keyboard,
    FOLDERS_PER_PAGE,
)


def test_folder_select_keyboard_shows_folders():
    """Keyboard shows folder buttons."""
    folders = ["alpha", "beta", "gamma"]
    kb = folder_select_keyboard(folders, page=0, total_pages=1)

    # Flatten buttons
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    texts = [btn.text for btn in buttons]

    assert "alpha" in texts
    assert "beta" in texts
    assert "gamma" in texts


def test_folder_select_keyboard_callback_data():
    """Folder buttons have correct callback_data."""
    folders = ["my-project"]
    kb = folder_select_keyboard(folders, page=0, total_pages=1)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    folder_btn = next(b for b in buttons if b.text == "my-project")

    assert folder_btn.callback_data == "folder:select:my-project"


def test_folder_select_keyboard_pagination():
    """Pagination buttons appear when needed."""
    folders = ["project"]
    kb = folder_select_keyboard(folders, page=1, total_pages=3)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "folder:page:0" in callbacks  # prev
    assert "folder:page:2" in callbacks  # next


def test_folder_select_keyboard_no_prev_on_first_page():
    """No prev button on first page."""
    folders = ["project"]
    kb = folder_select_keyboard(folders, page=0, total_pages=2)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "folder:page:-1" not in callbacks
    assert "folder:page:1" in callbacks


def test_folder_select_keyboard_has_view_connected():
    """View connected button present."""
    folders = ["project"]
    kb = folder_select_keyboard(folders, page=0, total_pages=1)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "folder:view_connected" in callbacks


def test_folder_select_keyboard_has_go_back():
    """Go back button present."""
    folders = ["project"]
    kb = folder_select_keyboard(folders, page=0, total_pages=1)

    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "folder:back" in callbacks
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/keyboards/test_folder_select.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/codogram/keyboards/setup/folder_select.py
"""Folder selection keyboard with pagination."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings

FOLDERS_PER_PAGE = 10


def folder_select_keyboard(
    folders: list[str],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Create folder selection keyboard with pagination.

    Args:
        folders: Folder names for current page
        page: Current page (0-indexed)
        total_pages: Total number of pages
    """
    rows = []

    # Folder buttons (one per row for readability)
    for folder in folders:
        # Truncate long names
        display_name = folder if len(folder) <= 30 else folder[:27] + "..."
        rows.append([
            InlineKeyboardButton(
                text=display_name,
                callback_data=f"folder:select:{folder}",
            )
        ])

    # Pagination row (if needed)
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="<",
                callback_data=f"folder:page:{page - 1}",
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="noop",  # non-interactive
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text=">",
                callback_data=f"folder:page:{page + 1}",
            ))
        rows.append(nav_row)

    # View connected button
    rows.append([
        InlineKeyboardButton(
            text=strings.BTN_VIEW_CONNECTED,
            callback_data="folder:view_connected",
        )
    ])

    # Go back button
    rows.append([
        InlineKeyboardButton(
            text=strings.BTN_GO_BACK,
            callback_data="folder:back",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def connected_projects_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for view connected projects screen."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.BTN_BACK_TO_FOLDERS,
            callback_data="folder:back_connected",
        )]
    ])
```

**Step 4: Update keyboards/setup/__init__.py**

```python
# src/codogram/keyboards/setup/__init__.py
from .common import go_back_keyboard
from .setup_type import admin_check_keyboard, setup_type_keyboard
from .folder_select import folder_select_keyboard, connected_projects_keyboard, FOLDERS_PER_PAGE

__all__ = [
    "setup_type_keyboard",
    "admin_check_keyboard",
    "go_back_keyboard",
    "folder_select_keyboard",
    "connected_projects_keyboard",
    "FOLDERS_PER_PAGE",
]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/keyboards/test_folder_select.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/keyboards/setup/folder_select.py tests/keyboards/test_folder_select.py
git commit -m "feat(setup): add folder select keyboard with pagination"
```

---

### Task 14: Add get_chat_link Utility

**Files:**
- Modify: `src/codogram/services/setup/folder_list.py`
- Test: `tests/services/test_folder_list.py`

**Step 1: Add test**

```python
# Add to tests/services/test_folder_list.py
from codogram.services.setup.folder_list import get_chat_link


def test_get_chat_link_supergroup():
    """Supergroup chat_id converts to t.me/c link."""
    link = get_chat_link(-1001234567890, "supergroup")
    assert link == "https://t.me/c/1234567890"


def test_get_chat_link_regular_group_returns_none():
    """Regular groups don't have stable links."""
    link = get_chat_link(-123456789, "group")
    assert link is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_folder_list.py::test_get_chat_link_supergroup -v`
Expected: FAIL

**Step 3: Add implementation**

```python
# Add to src/codogram/services/setup/folder_list.py

def get_chat_link(chat_id: int, chat_type: str) -> str | None:
    """Generate t.me link for a chat.

    Args:
        chat_id: Telegram chat ID
        chat_type: Chat type (supergroup, group, etc.)

    Returns:
        URL string or None if not possible
    """
    if chat_type == "supergroup":
        # Supergroups have t.me/c/{id} links
        # chat_id = -1001234567890 → link_id = 1234567890
        link_id = str(abs(chat_id))[3:]  # remove -100 prefix
        return f"https://t.me/c/{link_id}"

    # Regular groups don't have stable links
    return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_folder_list.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/setup/folder_list.py tests/services/test_folder_list.py
git commit -m "feat(setup): add get_chat_link utility"
```

---

### Task 15: Add Connect Flow Handlers

**Files:**
- Create: `src/codogram/handlers/setup/connect_flow.py`

**Step 1: Write implementation**

```python
# src/codogram/handlers/setup/connect_flow.py
"""Connect to existing folder flow handlers."""
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...config import settings
from ...domain.states import SetupFlow
from ...keyboards.setup import (
    setup_type_keyboard,
    folder_select_keyboard,
    connected_projects_keyboard,
    go_back_keyboard,
    FOLDERS_PER_PAGE,
)
from ...services.setup import list_available_folders, get_connected_folders, get_chat_link
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_connect")


async def show_folder_selection(message: Message, state: FSMContext, page: int = 0):
    """Show folder selection with pagination."""
    base_dir = Path(settings.base_dir).expanduser()
    connected = set(get_connected_folders().keys())

    folders = list_available_folders(base_dir, connected)

    if not folders:
        # No folders available
        if connected:
            text = strings.SETUP_FOLDER_ALL_CONNECTED
        else:
            text = strings.SETUP_FOLDER_EMPTY.format(base_dir=settings.base_dir)

        await message.edit_text(
            text,
            reply_markup=go_back_keyboard("folder:back"),
        )
        return

    # Calculate pagination
    total_pages = (len(folders) + FOLDERS_PER_PAGE - 1) // FOLDERS_PER_PAGE
    page = max(0, min(page, total_pages - 1))  # clamp

    start = page * FOLDERS_PER_PAGE
    end = start + FOLDERS_PER_PAGE
    page_folders = folders[start:end]

    await message.edit_text(
        strings.SETUP_FOLDER_SELECT,
        reply_markup=folder_select_keyboard(page_folders, page, total_pages),
    )


@router.callback_query(
    SetupFlow.awaiting_folder_select,
    F.data.startswith("folder:page:")
)
async def on_folder_page(callback: CallbackQuery, state: FSMContext):
    """Handle pagination buttons."""
    await callback.answer()

    page = int(callback.data.split(":")[-1])
    await show_folder_selection(callback.message, state, page)


@router.callback_query(
    SetupFlow.awaiting_folder_select,
    F.data.startswith("folder:select:")
)
async def on_folder_selected(callback: CallbackQuery, state: FSMContext):
    """Handle folder selection."""
    await callback.answer()

    folder_name = callback.data.split(":", 2)[-1]

    # Verify folder still exists
    base_dir = Path(settings.base_dir).expanduser()
    target_dir = base_dir / folder_name

    if not target_dir.exists():
        await callback.message.edit_text(
            strings.SETUP_FOLDER_NOT_FOUND.format(name=folder_name),
            reply_markup=go_back_keyboard("folder:back"),
        )
        return

    await state.update_data(
        project_name=folder_name,
        target_dir=str(target_dir),
    )

    # Check if rename needed
    chat_title = callback.message.chat.title or ""

    if chat_title != folder_name:
        await state.set_state(SetupFlow.awaiting_rename_confirm)
        await state.update_data(rename_to=folder_name)

        from ...keyboards.setup.confirm import rename_confirm_keyboard
        await callback.message.edit_text(
            strings.SETUP_RENAME_PROMPT.format(name=folder_name),
            reply_markup=rename_confirm_keyboard(),
        )
    else:
        # Check git status
        await _check_git_and_proceed(callback.message, state, target_dir)


async def _check_git_and_proceed(message: Message, state: FSMContext, target_dir: Path):
    """Check if folder has git and proceed accordingly."""
    has_git = (target_dir / ".git").exists()

    if has_git:
        # Proceed directly to launch
        from .launch import do_launch
        await do_launch(message, state)
    else:
        # Ask about git
        await state.set_state(SetupFlow.awaiting_git_choice)

        from ...keyboards.setup.git_choice import git_choice_keyboard
        data = await state.get_data()
        folder_name = data["project_name"]

        await message.edit_text(
            strings.SETUP_GIT_CHOICE.format(folder=folder_name),
            reply_markup=git_choice_keyboard(),
        )


@router.callback_query(
    SetupFlow.awaiting_folder_select,
    F.data == "folder:view_connected"
)
async def on_view_connected(callback: CallbackQuery, state: FSMContext):
    """Show connected projects."""
    await callback.answer()
    await state.set_state(SetupFlow.viewing_connected_projects)

    connected = get_connected_folders()

    if not connected:
        text = f"{strings.SETUP_CONNECTED_HEADER}\n\n{strings.SETUP_CONNECTED_EMPTY}"
    else:
        lines = [strings.SETUP_CONNECTED_HEADER, ""]

        from ...session_manager import ProjectManager
        pm = ProjectManager()

        for folder_name, chat_id in connected.items():
            project = pm.projects.get(folder_name, {})
            chat_title = project.get("chat_title", folder_name)
            chat_type = project.get("chat_type", "group")

            link = get_chat_link(chat_id, chat_type)
            if link:
                lines.append(f"• {folder_name} → [{chat_title}]({link})")
            else:
                lines.append(f"• {folder_name} → {chat_title} {strings.SETUP_CONNECTED_NO_LINK}")

        lines.append("")
        lines.append(strings.SETUP_CONNECTED_TAP_HINT)
        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=connected_projects_keyboard(),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


@router.callback_query(
    SetupFlow.viewing_connected_projects,
    F.data == "folder:back_connected"
)
async def on_back_from_connected(callback: CallbackQuery, state: FSMContext):
    """Go back to folder selection."""
    await callback.answer()
    await state.set_state(SetupFlow.awaiting_folder_select)
    await show_folder_selection(callback.message, state, page=0)


@router.callback_query(
    SetupFlow.awaiting_folder_select,
    F.data == "folder:back"
)
async def on_folder_back(callback: CallbackQuery, state: FSMContext):
    """Go back to setup type selection."""
    await callback.answer()
    await state.set_state(SetupFlow.awaiting_setup_type)
    await callback.message.edit_text(
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )


@router.message(SetupFlow.awaiting_folder_select)
async def on_folder_text_input(message: Message, state: FSMContext):
    """Handle text input during folder selection (not expected)."""
    await message.answer(
        strings.SETUP_FOLDER_USE_BUTTONS,
        parse_mode="MarkdownV2",
    )
```

**Step 2: Update handlers/setup/__init__.py**

```python
# Add to src/codogram/handlers/setup/__init__.py
from . import connect_flow  # noqa: E402, F401
setup_router.include_router(connect_flow.router)
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/setup/connect_flow.py src/codogram/handlers/setup/__init__.py
git commit -m "feat(setup): add connect flow handlers with pagination"
```

---

## Phase 6: New Project Flow

### Task 16: Add Git Choice Keyboard

**Files:**
- Create: `src/codogram/keyboards/setup/git_choice.py`
- Test: `tests/keyboards/test_git_choice.py`

**Step 1: Write the failing test**

```python
# tests/keyboards/test_git_choice.py
from codogram.keyboards.setup.git_choice import git_choice_keyboard


def test_git_choice_keyboard_has_all_options():
    """Git choice keyboard has all 4 options."""
    kb = git_choice_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "git:init" in callbacks
    assert "git:gh" in callbacks
    assert "git:clone" in callbacks
    assert "git:none" in callbacks


def test_git_choice_keyboard_has_go_back():
    """Git choice keyboard has go back button."""
    kb = git_choice_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "git:back" in callbacks
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/keyboards/test_git_choice.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/codogram/keyboards/setup/git_choice.py
"""Git setup choice keyboard."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings


def git_choice_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for git setup options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_GIT_INIT, callback_data="git:init")],
        [InlineKeyboardButton(text=strings.BTN_GIT_GH, callback_data="git:gh")],
        [InlineKeyboardButton(text=strings.BTN_GIT_CLONE, callback_data="git:clone")],
        [InlineKeyboardButton(text=strings.BTN_GIT_NONE, callback_data="git:none")],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="git:back")],
    ])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/keyboards/test_git_choice.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/keyboards/setup/git_choice.py tests/keyboards/test_git_choice.py
git commit -m "feat(setup): add git choice keyboard"
```

---

### Task 17: Add Confirm Keyboard

**Files:**
- Create: `src/codogram/keyboards/setup/confirm.py`
- Test: `tests/keyboards/test_confirm.py`

**Step 1: Write the failing test**

```python
# tests/keyboards/test_confirm.py
from codogram.keyboards.setup.confirm import (
    rename_confirm_keyboard,
    folder_exists_keyboard,
)


def test_rename_confirm_keyboard():
    """Rename confirm has Yes/No buttons."""
    kb = rename_confirm_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "rename:yes" in callbacks
    assert "rename:no" in callbacks


def test_folder_exists_keyboard():
    """Folder exists has Use existing / Different name."""
    kb = folder_exists_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]

    assert "exists:use" in callbacks
    assert "exists:rename" in callbacks
    assert "exists:back" in callbacks
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/keyboards/test_confirm.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/codogram/keyboards/setup/confirm.py
"""Confirmation keyboards for setup flow."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ... import strings


def rename_confirm_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for rename confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_RENAME_YES, callback_data="rename:yes"),
            InlineKeyboardButton(text=strings.BTN_RENAME_NO, callback_data="rename:no"),
        ],
    ])


def folder_exists_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for folder exists scenario."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=strings.BTN_USE_EXISTING, callback_data="exists:use")],
        [InlineKeyboardButton(text=strings.BTN_DIFFERENT_NAME, callback_data="exists:rename")],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="exists:back")],
    ])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/keyboards/test_confirm.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/keyboards/setup/confirm.py tests/keyboards/test_confirm.py
git commit -m "feat(setup): add confirmation keyboards"
```

---

### Task 18: Add New Project Flow Handlers

**Files:**
- Create: `src/codogram/handlers/setup/new_project_flow.py`

**Step 1: Write implementation**

```python
# src/codogram/handlers/setup/new_project_flow.py
"""New project flow handlers."""
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...config import settings
from ...domain.states import SetupFlow
from ...domain.validators import sanitize_project_name
from ...keyboards.setup import setup_type_keyboard, go_back_keyboard
from ...keyboards.setup.git_choice import git_choice_keyboard
from ...keyboards.setup.confirm import rename_confirm_keyboard, folder_exists_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_new_project")


async def show_project_name_prompt(message: Message, state: FSMContext):
    """Show project name prompt with suggested name."""
    chat_title = message.chat.title or ""
    suggested = sanitize_project_name(chat_title)

    if suggested:
        text = strings.SETUP_PROJECT_NAME_PROMPT.format(suggested=suggested)
        # Add button for suggested name
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=suggested, callback_data=f"name:use:{suggested}")],
            [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="name:back")],
        ])
    else:
        text = strings.SETUP_PROJECT_NAME_PROMPT.format(suggested="(enter manually)")
        kb = go_back_keyboard("name:back")

    await message.edit_text(text, reply_markup=kb)


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data.startswith("name:use:")
)
async def on_suggested_name(callback: CallbackQuery, state: FSMContext):
    """Use suggested project name."""
    await callback.answer()

    name = callback.data.split(":", 2)[-1]
    await _process_project_name(callback.message, state, name, is_suggested=True)


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data == "name:back"
)
async def on_name_back(callback: CallbackQuery, state: FSMContext):
    """Go back to setup type."""
    await callback.answer()
    await state.set_state(SetupFlow.awaiting_setup_type)
    await callback.message.edit_text(
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )


@router.message(SetupFlow.awaiting_project_name)
async def on_project_name_input(message: Message, state: FSMContext):
    """Handle custom project name input."""
    name = message.text.strip()

    # Validate name
    sanitized = sanitize_project_name(name)
    if not sanitized or sanitized != name:
        await message.answer(
            strings.SETUP_PROJECT_NAME_INVALID,
            reply_markup=go_back_keyboard("name:back"),
            parse_mode="MarkdownV2",
        )
        return

    await _process_project_name(message, state, name, is_suggested=False)


async def _process_project_name(
    message: Message,
    state: FSMContext,
    name: str,
    is_suggested: bool,
):
    """Process validated project name."""
    base_dir = Path(settings.base_dir).expanduser()
    target_dir = base_dir / name

    await state.update_data(
        project_name=name,
        target_dir=str(target_dir),
    )

    # Check if folder exists
    if target_dir.exists():
        await message.edit_text(
            strings.SETUP_PROJECT_EXISTS.format(name=name),
            reply_markup=folder_exists_keyboard(),
        )
        return

    # Custom name → ask for rename
    if not is_suggested:
        chat_title = message.chat.title or ""
        if chat_title != name:
            await state.set_state(SetupFlow.awaiting_rename_confirm)
            await state.update_data(rename_to=name)
            await message.edit_text(
                strings.SETUP_RENAME_PROMPT.format(name=name),
                reply_markup=rename_confirm_keyboard(),
            )
            return

    # Proceed to git choice
    await state.set_state(SetupFlow.awaiting_git_choice)
    await message.edit_text(
        strings.SETUP_GIT_CHOICE.format(folder=name),
        reply_markup=git_choice_keyboard(),
    )


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data == "exists:use"
)
async def on_use_existing(callback: CallbackQuery, state: FSMContext):
    """Use existing folder."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])

    # Check git
    has_git = (target_dir / ".git").exists()

    if has_git:
        from .launch import do_launch
        await do_launch(callback.message, state)
    else:
        await state.set_state(SetupFlow.awaiting_git_choice)
        await callback.message.edit_text(
            strings.SETUP_GIT_CHOICE.format(folder=data["project_name"]),
            reply_markup=git_choice_keyboard(),
        )


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data == "exists:rename"
)
async def on_different_name(callback: CallbackQuery, state: FSMContext):
    """Ask for different name."""
    await callback.answer()
    await show_project_name_prompt(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_project_name,
    F.data == "exists:back"
)
async def on_exists_back(callback: CallbackQuery, state: FSMContext):
    """Go back from folder exists."""
    await callback.answer()
    await state.set_state(SetupFlow.awaiting_setup_type)
    await callback.message.edit_text(
        strings.SETUP_CHOOSE_TYPE,
        reply_markup=setup_type_keyboard(),
    )
```

**Step 2: Update handlers __init__.py**

```python
from . import new_project_flow  # noqa: E402, F401
setup_router.include_router(new_project_flow.router)
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/setup/new_project_flow.py
git commit -m "feat(setup): add new project flow handlers"
```

---

### Task 19: Add Git Operations Service

**Files:**
- Create: `src/codogram/services/setup/git_operations.py`
- Test: `tests/services/test_git_operations.py`

**Step 1: Write the failing test**

```python
# tests/services/test_git_operations.py
import pytest
from unittest.mock import patch, AsyncMock

from codogram.services.setup.git_operations import (
    git_init,
    check_gh_cli,
    extract_project_name_from_url,
)


def test_extract_project_name_https():
    """Extract name from HTTPS URL."""
    url = "https://github.com/user/awesome-project.git"
    assert extract_project_name_from_url(url) == "awesome-project"


def test_extract_project_name_ssh():
    """Extract name from SSH URL."""
    url = "git@github.com:user/awesome-project.git"
    assert extract_project_name_from_url(url) == "awesome-project"


def test_extract_project_name_no_git_suffix():
    """Extract name without .git suffix."""
    url = "https://github.com/user/awesome-project"
    assert extract_project_name_from_url(url) == "awesome-project"


@pytest.mark.asyncio
async def test_git_init_creates_repo(tmp_path):
    """git_init creates .git directory."""
    result = await git_init(tmp_path)
    assert result.success
    assert (tmp_path / ".git").exists()


@pytest.mark.asyncio
async def test_check_gh_cli_not_installed():
    """check_gh_cli returns error when gh not found."""
    with patch("shutil.which", return_value=None):
        result = await check_gh_cli()
        assert not result.success
        assert "not installed" in result.error.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_git_operations.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/codogram/services/setup/git_operations.py
"""Git operations service."""
import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GitResult:
    """Result of a git operation."""
    success: bool
    error: str | None = None
    output: str | None = None


def extract_project_name_from_url(url: str) -> str | None:
    """Extract project name from git URL.

    Examples:
        https://github.com/user/awesome-project.git -> awesome-project
        git@github.com:user/awesome-project.git -> awesome-project
    """
    # HTTPS format
    https_match = re.search(r'/([^/]+?)(?:\.git)?$', url)
    if https_match:
        name = https_match.group(1)
        if name.endswith(".git"):
            name = name[:-4]
        return name

    # SSH format
    ssh_match = re.search(r':(?:[^/]+/)?([^/]+?)(?:\.git)?$', url)
    if ssh_match:
        name = ssh_match.group(1)
        if name.endswith(".git"):
            name = name[:-4]
        return name

    return None


async def git_init(target_dir: Path) -> GitResult:
    """Initialize git repository.

    Args:
        target_dir: Directory to initialize

    Returns:
        GitResult with success/error
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "git", "init",
            cwd=str(target_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return GitResult(
                success=False,
                error=stderr.decode().strip() or "git init failed",
            )

        return GitResult(success=True, output=stdout.decode().strip())

    except Exception as e:
        logger.exception(f"git init failed: {e}")
        return GitResult(success=False, error=str(e))


async def check_gh_cli() -> GitResult:
    """Check if gh CLI is installed and authenticated.

    Returns:
        GitResult with success if gh is ready to use
    """
    # Check if installed
    if not shutil.which("gh"):
        return GitResult(
            success=False,
            error="gh CLI not installed. Install from https://cli.github.com",
        )

    # Check if authenticated
    try:
        process = await asyncio.create_subprocess_exec(
            "gh", "auth", "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            return GitResult(
                success=False,
                error="gh CLI not authenticated. Run `gh auth login` first",
            )

        return GitResult(success=True)

    except Exception as e:
        return GitResult(success=False, error=str(e))


async def gh_repo_create(target_dir: Path, name: str, private: bool = True) -> GitResult:
    """Create GitHub repo using gh CLI.

    Args:
        target_dir: Local directory
        name: Repository name
        private: Create private repo (default True)
    """
    check = await check_gh_cli()
    if not check.success:
        return check

    try:
        args = ["gh", "repo", "create", name, "--source", str(target_dir)]
        if private:
            args.append("--private")
        else:
            args.append("--public")

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return GitResult(
                success=False,
                error=stderr.decode().strip() or "gh repo create failed",
            )

        return GitResult(success=True, output=stdout.decode().strip())

    except Exception as e:
        logger.exception(f"gh repo create failed: {e}")
        return GitResult(success=False, error=str(e))
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_git_operations.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/setup/git_operations.py tests/services/test_git_operations.py
git commit -m "feat(setup): add git operations service"
```

---

### Task 20: Add Git Choice Handlers

**Files:**
- Modify: `src/codogram/handlers/setup/new_project_flow.py`

**Step 1: Add git choice handlers**

```python
# Add to src/codogram/handlers/setup/new_project_flow.py

@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:init"
)
async def on_git_init(callback: CallbackQuery, state: FSMContext):
    """Initialize git repository."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])

    # Create directory if needed
    if not target_dir.exists():
        target_dir.mkdir(parents=True)

    from ...services.setup.git_operations import git_init
    result = await git_init(target_dir)

    if not result.success:
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} git init failed: {result.error}",
            reply_markup=go_back_keyboard("git:back"),
        )
        return

    await state.update_data(git_choice="init")

    from .launch import do_launch
    await do_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:gh"
)
async def on_git_gh(callback: CallbackQuery, state: FSMContext):
    """Git init + gh repo create."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])
    project_name = data["project_name"]

    # Check gh first
    from ...services.setup.git_operations import check_gh_cli, git_init, gh_repo_create

    check = await check_gh_cli()
    if not check.success:
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} {check.error}",
            reply_markup=git_choice_keyboard(),
            parse_mode="MarkdownV2",
        )
        return

    # Create directory
    if not target_dir.exists():
        target_dir.mkdir(parents=True)

    # Git init
    init_result = await git_init(target_dir)
    if not init_result.success:
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} git init failed: {init_result.error}",
            reply_markup=go_back_keyboard("git:back"),
        )
        return

    # Create GitHub repo
    gh_result = await gh_repo_create(target_dir, project_name)
    if not gh_result.success:
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} gh repo create failed: {gh_result.error}",
            reply_markup=go_back_keyboard("git:back"),
        )
        return

    await state.update_data(git_choice="gh")

    from .launch import do_launch
    await do_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:clone"
)
async def on_git_clone(callback: CallbackQuery, state: FSMContext):
    """Switch to clone flow."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])

    # Check if folder is empty
    if target_dir.exists() and any(target_dir.iterdir()):
        await callback.message.edit_text(
            f"{strings.STATUS_ERR} Folder not empty, can't clone",
            reply_markup=go_back_keyboard("git:back"),
        )
        return

    # Switch to clone flow
    await state.set_state(SetupFlow.awaiting_clone_url)
    await state.update_data(setup_type="clone", clone_into_existing=True)

    await callback.message.edit_text(
        strings.SETUP_CLONE_URL_PROMPT,
        reply_markup=go_back_keyboard("clone:back"),
    )


@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:none"
)
async def on_git_none(callback: CallbackQuery, state: FSMContext):
    """No git setup."""
    await callback.answer()

    data = await state.get_data()
    target_dir = Path(data["target_dir"])

    # Create directory if needed
    if not target_dir.exists():
        target_dir.mkdir(parents=True)

    await state.update_data(git_choice="none")

    from .launch import do_launch
    await do_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_git_choice,
    F.data == "git:back"
)
async def on_git_back(callback: CallbackQuery, state: FSMContext):
    """Go back from git choice."""
    await callback.answer()

    data = await state.get_data()
    setup_type = data.get("setup_type")

    if setup_type == "connect":
        # Back to folder selection
        await state.set_state(SetupFlow.awaiting_folder_select)
        from .connect_flow import show_folder_selection
        await show_folder_selection(callback.message, state)
    else:
        # Back to project name
        await state.set_state(SetupFlow.awaiting_project_name)
        await show_project_name_prompt(callback.message, state)
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/setup/new_project_flow.py
git commit -m "feat(setup): add git choice handlers"
```

---

## Phase 7: Launch & Rename

### Task 21: Add Chat Rename Service

**Files:**
- Create: `src/codogram/services/setup/chat_rename.py`
- Test: `tests/services/test_chat_rename.py`

**Step 1: Write the failing test**

```python
# tests/services/test_chat_rename.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from codogram.services.setup.chat_rename import rename_chat_safe


@pytest.mark.asyncio
async def test_rename_chat_success():
    """rename_chat_safe returns True on success."""
    bot = AsyncMock()
    bot.set_chat_title = AsyncMock()

    result = await rename_chat_safe(bot, -1001234567890, "New Title")
    assert result is True
    bot.set_chat_title.assert_called_once()


@pytest.mark.asyncio
async def test_rename_chat_retry_after():
    """rename_chat_safe retries on TelegramRetryAfter."""
    bot = AsyncMock()

    # First call raises retry, second succeeds
    error = TelegramRetryAfter(method=MagicMock(), message="Retry after 1 seconds")
    error.retry_after = 0.1  # fast for test

    bot.set_chat_title = AsyncMock(side_effect=[error, None])

    result = await rename_chat_safe(bot, -1001234567890, "New Title")
    assert result is True
    assert bot.set_chat_title.call_count == 2


@pytest.mark.asyncio
async def test_rename_chat_bad_request_no_retry():
    """rename_chat_safe doesn't retry TelegramBadRequest."""
    bot = AsyncMock()

    error = TelegramBadRequest(method=MagicMock(), message="Not enough rights")
    bot.set_chat_title = AsyncMock(side_effect=error)

    result = await rename_chat_safe(bot, -1001234567890, "New Title")
    assert result is False
    assert bot.set_chat_title.call_count == 1  # No retry
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_chat_rename.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/codogram/services/setup/chat_rename.py
"""Chat rename service with retry logic."""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest, TelegramAPIError

logger = logging.getLogger(__name__)


async def rename_chat_safe(
    bot: Bot,
    chat_id: int,
    title: str,
    max_retries: int = 3,
) -> bool:
    """Try to rename chat with exponential backoff.

    Args:
        bot: Bot instance
        chat_id: Chat to rename
        title: New chat title
        max_retries: Maximum retry attempts

    Returns:
        True if renamed successfully, False otherwise
    """
    for attempt in range(max_retries):
        try:
            await bot.set_chat_title(chat_id, title)
            return True

        except TelegramRetryAfter as e:
            # Rate limited — wait and retry
            if attempt < max_retries - 1:
                logger.info(f"Rename rate limited, waiting {e.retry_after}s")
                await asyncio.sleep(e.retry_after)
                continue
            logger.warning(f"Rename failed after {max_retries} retries: rate limited")
            return False

        except TelegramBadRequest as e:
            # Not enough rights, chat title too long — no retry
            logger.warning(f"Rename failed: {e}")
            return False

        except TelegramAPIError as e:
            # Network error — retry with backoff
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.info(f"Rename failed ({e}), retrying in {wait_time}s")
                await asyncio.sleep(wait_time)
                continue
            logger.warning(f"Rename failed after {max_retries} retries: {e}")
            return False

    return False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_chat_rename.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/setup/chat_rename.py tests/services/test_chat_rename.py
git commit -m "feat(setup): add chat rename service with retry"
```

---

### Task 22: Add Rename Confirm Handlers

**Files:**
- Create: `src/codogram/handlers/setup/rename.py`

**Step 1: Write implementation**

```python
# src/codogram/handlers/setup/rename.py
"""Rename confirmation handlers."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...domain.states import SetupFlow
from ...services.setup.chat_rename import rename_chat_safe
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_rename")


@router.callback_query(
    SetupFlow.awaiting_rename_confirm,
    F.data == "rename:yes"
)
async def on_rename_yes(callback: CallbackQuery, state: FSMContext):
    """Confirm chat rename."""
    await callback.answer()

    data = await state.get_data()
    rename_to = data.get("rename_to")

    if rename_to:
        success = await rename_chat_safe(
            callback.bot,
            callback.message.chat.id,
            rename_to,
        )

        if not success:
            # Warn but continue
            await callback.message.answer(
                strings.SETUP_RENAME_FAILED,
                parse_mode="MarkdownV2",
            )

    # Proceed to launch
    from .launch import do_launch
    await do_launch(callback.message, state)


@router.callback_query(
    SetupFlow.awaiting_rename_confirm,
    F.data == "rename:no"
)
async def on_rename_no(callback: CallbackQuery, state: FSMContext):
    """Skip rename."""
    await callback.answer()

    # Proceed to launch
    from .launch import do_launch
    await do_launch(callback.message, state)
```

**Step 2: Update handlers __init__.py**

```python
from . import rename  # noqa: E402, F401
setup_router.include_router(rename.router)
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/setup/rename.py src/codogram/handlers/setup/__init__.py
git commit -m "feat(setup): add rename confirmation handlers"
```

---

### Task 23: Add Project Setup Service

**Files:**
- Create: `src/codogram/services/setup/project_setup.py`

**Step 1: Write implementation**

```python
# src/codogram/services/setup/project_setup.py
"""Project setup service with atomic operations and rollback."""
import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from ...config import settings
from ...session_manager import ProjectManager
from ...tmux import create_session_name, create_tmux_session
from ...services.launch import launch_claude

logger = logging.getLogger(__name__)


@dataclass
class SetupResult:
    """Result of project setup."""
    success: bool
    error: str | None = None
    tmux_name: str | None = None


async def setup_project(
    project_name: str,
    target_dir: Path,
    chat_id: int,
    chat_title: str,
    chat_type: str,
) -> SetupResult:
    """Set up project with atomic operations.

    Phases:
    1. Filesystem - create dir if needed (rollback: delete)
    2. Runtime - create tmux, launch Claude, save config

    Args:
        project_name: Project/folder name
        target_dir: Full path to project directory
        chat_id: Telegram chat ID
        chat_title: Chat title for config
        chat_type: Chat type (group/supergroup)

    Returns:
        SetupResult with success/error
    """
    created_dir = False
    tmux_name = None

    try:
        # Phase 1: Filesystem
        if not target_dir.exists():
            target_dir.mkdir(parents=True)
            created_dir = True
            logger.info(f"Created directory: {target_dir}")

        # Phase 2: Runtime
        tmux_name = create_session_name(project_name)

        # Create tmux session
        success = await create_tmux_session(tmux_name, str(target_dir))
        if not success:
            raise RuntimeError("Failed to create tmux session")

        # Launch Claude
        launch_result = await launch_claude(tmux_name)
        if not launch_result.success:
            raise RuntimeError(f"Failed to launch Claude: {launch_result.error}")

        # Save to config
        pm = ProjectManager()
        pm.register_project(
            project_name=project_name,
            chat_id=chat_id,
            chat_title=chat_title,
            chat_type=chat_type,
            tmux_name=tmux_name,
            cwd=str(target_dir),
        )

        return SetupResult(success=True, tmux_name=tmux_name)

    except Exception as e:
        logger.exception(f"Project setup failed: {e}")

        # Rollback Phase 2 - kill tmux if created
        if tmux_name:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "tmux", "kill-session", "-t", tmux_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except Exception:
                pass

        # Rollback Phase 1 - delete dir if we created it
        if created_dir and target_dir.exists():
            try:
                shutil.rmtree(target_dir)
                logger.info(f"Rolled back: deleted {target_dir}")
            except Exception as cleanup_error:
                logger.warning(f"Rollback failed: {cleanup_error}")

        return SetupResult(success=False, error=str(e))
```

**Step 2: Commit**

```bash
git add src/codogram/services/setup/project_setup.py
git commit -m "feat(setup): add project setup service with rollback"
```

---

### Task 24: Add Launch Handler

**Files:**
- Create: `src/codogram/handlers/setup/launch.py`

**Step 1: Write implementation**

```python
# src/codogram/handlers/setup/launch.py
"""Launch phase handler."""
import logging
from pathlib import Path

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ...domain.states import SetupFlow
from ...services.setup.project_setup import setup_project
from ...services.menu import register_menu_for_chat, BASIC_COMMANDS, FORUM_COMMANDS
from ...keyboards.setup import go_back_keyboard
from ... import strings

logger = logging.getLogger(__name__)

router = Router(name="setup_launch")


async def do_launch(message: Message, state: FSMContext):
    """Execute the launch phase.

    This is called from various flows after all setup is complete.
    """
    # Enter launching state (blocks user input)
    await state.set_state(SetupFlow.launching)

    data = await state.get_data()
    project_name = data["project_name"]
    target_dir = Path(data["target_dir"])

    chat = message.chat
    chat_id = chat.id
    chat_title = chat.title or project_name
    chat_type = chat.type

    # Show progress
    progress_msg = await message.answer(strings.SETUP_LAUNCH_PROGRESS)

    # Run setup
    result = await setup_project(
        project_name=project_name,
        target_dir=target_dir,
        chat_id=chat_id,
        chat_title=chat_title,
        chat_type=chat_type,
    )

    if not result.success:
        await progress_msg.edit_text(
            f"{strings.STATUS_ERR} Setup failed: {result.error}",
            reply_markup=go_back_keyboard("error:retry"),
        )
        return

    # Register appropriate menu
    is_forum = chat_type == "supergroup" and getattr(chat, "is_forum", False)
    await register_menu_for_chat(message.bot, chat_id, is_forum)

    # Clear FSM state
    await state.clear()

    # Success announcement
    await progress_msg.edit_text(
        strings.SETUP_LAUNCH_SUCCESS.format(
            project=project_name,
            tmux_name=result.tmux_name,
        ),
        parse_mode="MarkdownV2",
    )
```

**Step 2: Update handlers __init__.py**

```python
from . import launch  # noqa: E402, F401
setup_router.include_router(launch.router)
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/setup/launch.py src/codogram/handlers/setup/__init__.py
git commit -m "feat(setup): add launch handler with success announcement"
```

---

### Task 25: Add Menu Registration on Setup Enter

**Files:**
- Modify: `src/codogram/handlers/setup/triggers.py`

**Step 1: Add menu registration to _start_setup_flow**

```python
# Update _start_setup_flow in triggers.py

async def _start_setup_flow(event: ChatMemberUpdated, state: FSMContext):
    """Start the setup flow - check base_dir, then admin rights."""
    chat = event.chat
    bot = event.bot

    # Register SETUP_COMMANDS menu
    from ...services.menu import SETUP_COMMANDS
    from aiogram.types import BotCommandScopeChat

    scope = BotCommandScopeChat(chat_id=chat.id)
    await bot.set_my_commands(SETUP_COMMANDS, scope=scope)

    # Check admin rights
    has_rights = await check_bot_admin_rights(bot, chat.id)

    # ... rest of the function
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/setup/triggers.py
git commit -m "feat(setup): register SETUP_COMMANDS on setup enter"
```

---

## Phase 8: Middleware & Polish

### Task 26: Add Setup Blocker Middleware

**Files:**
- Create: `src/codogram/middleware/setup_blocker.py`
- Test: `tests/middleware/test_setup_blocker.py`

**Step 1: Write the failing test**

```python
# tests/middleware/test_setup_blocker.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from codogram.middleware.setup_blocker import SetupBlockerMiddleware


@pytest.mark.asyncio
async def test_allows_start_during_setup():
    """Commands /start, /reset_all, /help, /get_debug_ids allowed during setup."""
    middleware = SetupBlockerMiddleware()

    # Mock handler
    handler = AsyncMock()

    # Mock message with /start command
    message = MagicMock()
    message.text = "/start"

    # Mock state with SetupFlow active
    state = AsyncMock()
    state.get_state = AsyncMock(return_value="SetupFlow:awaiting_setup_type")

    data = {"state": state}

    await middleware(handler, message, data)

    # Handler should be called
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_blocks_other_commands_during_setup():
    """Other commands blocked during setup."""
    middleware = SetupBlockerMiddleware()

    handler = AsyncMock()

    message = MagicMock()
    message.text = "/settings"
    message.answer = AsyncMock()

    state = AsyncMock()
    state.get_state = AsyncMock(return_value="SetupFlow:awaiting_setup_type")

    data = {"state": state}

    await middleware(handler, message, data)

    # Handler should NOT be called
    handler.assert_not_called()
    # Should send blocking message
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_allows_all_commands_outside_setup():
    """All commands allowed when not in setup."""
    middleware = SetupBlockerMiddleware()

    handler = AsyncMock()

    message = MagicMock()
    message.text = "/settings"

    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)

    data = {"state": state}

    await middleware(handler, message, data)

    handler.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/middleware/test_setup_blocker.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/codogram/middleware/setup_blocker.py
"""Middleware to block non-setup commands during setup flow."""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from .. import strings

logger = logging.getLogger(__name__)

# Commands allowed during setup
ALLOWED_DURING_SETUP = {"/start", "/reset_all", "/help", "/get_debug_ids"}


class SetupBlockerMiddleware(BaseMiddleware):
    """Block commands during setup flow.

    Only allows /start, /reset_all, /help, /get_debug_ids while
    any SetupFlow state is active.
    """

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # Only process commands
        if not event.text or not event.text.startswith("/"):
            return await handler(event, data)

        # Get FSM state
        state = data.get("state")
        if not state:
            return await handler(event, data)

        current_state = await state.get_state()

        # Check if in setup flow
        if current_state and current_state.startswith("SetupFlow:"):
            # Extract command (without @botname suffix)
            command = event.text.split()[0].split("@")[0]

            if command not in ALLOWED_DURING_SETUP:
                logger.debug(f"Blocked {command} during setup")
                await event.answer(
                    strings.SETUP_COMMAND_BLOCKED,
                    parse_mode="MarkdownV2",
                )
                return

        return await handler(event, data)
```

**Step 4: Add missing string**

```python
# Add to strings.py
SETUP_COMMAND_BLOCKED = f"""{STATUS_WARN} Complete project setup first

Available commands:
• /start — restart setup
• /reset\\_all — cancel setup
• /help — get help"""
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/middleware/test_setup_blocker.py -v`
Expected: PASS

**Step 6: Commit**

```bash
mkdir -p tests/middleware
touch tests/middleware/__init__.py
git add src/codogram/middleware/setup_blocker.py tests/middleware/
git commit -m "feat(setup): add setup blocker middleware"
```

---

### Task 27: Register Middleware in Main

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Add middleware registration**

Find the dispatcher setup section and add:

```python
from .middleware.setup_blocker import SetupBlockerMiddleware

# In setup function, after dp is created:
dp.message.middleware(SetupBlockerMiddleware())
```

**Step 2: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(setup): register setup blocker middleware"
```

---

### Task 28: Add Base Dir Check to Triggers

**Files:**
- Modify: `src/codogram/handlers/setup/triggers.py`
- Create: `src/codogram/services/setup/base_dir.py`

**Step 1: Create base_dir service**

```python
# src/codogram/services/setup/base_dir.py
"""Base directory validation service."""
from pathlib import Path

from ...config import settings


def check_base_dir() -> Path | None:
    """Check if base_dir is configured and exists.

    Returns:
        Path to base_dir if valid, None otherwise
    """
    base_dir = settings.base_dir
    if not base_dir:
        return None

    path = Path(base_dir).expanduser()
    if not path.exists():
        return None

    return path
```

**Step 2: Update triggers.py**

```python
# Update _start_setup_flow in triggers.py

from ...services.setup.base_dir import check_base_dir

async def _start_setup_flow(event: ChatMemberUpdated, state: FSMContext):
    """Start the setup flow - check base_dir first, then admin rights."""
    chat = event.chat
    bot = event.bot

    # Check base_dir FIRST
    base_path = check_base_dir()
    if not base_path:
        await bot.send_message(
            chat.id,
            strings.SETUP_BASE_DIR_MISSING,
            parse_mode="MarkdownV2",
        )
        return  # Flow blocked

    # Register SETUP_COMMANDS menu
    from ...services.menu import SETUP_COMMANDS
    from aiogram.types import BotCommandScopeChat

    scope = BotCommandScopeChat(chat_id=chat.id)
    await bot.set_my_commands(SETUP_COMMANDS, scope=scope)

    # Check admin rights
    has_rights = await check_bot_admin_rights(bot, chat.id)

    # ... rest unchanged
```

**Step 3: Commit**

```bash
git add src/codogram/services/setup/base_dir.py src/codogram/handlers/setup/triggers.py
git commit -m "feat(setup): add base_dir check before setup flow"
```

---

## Phase 9: E2E Testing

### Task 29: E2E Test - Clone Flow

**Test via Telegram MCP:**

```
1. Ask user for test chat ID
2. Add bot to test chat (or use existing)
3. Verify: Bot shows "Grant admin rights" message
4. Grant admin rights
5. Verify: Bot shows Clone/Connect/New buttons
6. Click "Clone repository"
7. Send: https://github.com/user/test-repo.git
8. Verify: Clone progress, then success or rename prompt
9. If rename prompt, click Yes
10. Verify: Success message with tmux name
11. Verify: /settings works (setup complete)
```

**Expected strings to verify:**
- "Grant admin rights to continue"
- "How would you like to set up this project?"
- "Cloning repository..."
- "Project `...` ready"

---

### Task 30: E2E Test - Connect & New Flows

**Connect Flow:**
```
1. Click "Connect to existing folder"
2. Verify: Folder list with pagination
3. Click a folder
4. Verify: Rename prompt or git choice
5. Complete flow
6. Verify: Success
```

**New Project Flow:**
```
1. Click "Start new project"
2. Verify: Project name prompt with suggestion
3. Click suggested name or send custom
4. Verify: Git choice screen
5. Select "No git"
6. Verify: Success
```

**Edge cases to test:**
- /start during active setup (should restart)
- /settings during setup (should be blocked)
- Bot kicked during setup (verify cleanup)

---

## Execution Notes

**Test command:** `pytest tests/ -v --tb=short`

**Run bot for testing:** `./dev-run.sh`

**E2E test chat:** Ask user for test chat ID before testing

**Key files to reference:**
- Design: `docs/designs/2026-01-18-start-flow-v2.md`
- Existing start handler: `src/codogram/handlers/start.py`
- Existing start service: `src/codogram/services/start_flow.py`
- Existing validators: `src/codogram/domain/validators.py`
