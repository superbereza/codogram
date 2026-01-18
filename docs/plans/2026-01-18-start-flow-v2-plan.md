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

## Remaining Tasks (Summary)

Due to the comprehensive nature of this plan, here's a summary of remaining tasks:

### Task 11-15: Connect Flow
- `services/setup/folder_list.py` - list_available_folders()
- `keyboards/setup/folder_select.py` - pagination keyboard
- `handlers/setup/connect_flow.py` - folder selection handlers
- View connected projects screen

### Task 16-20: New Project Flow
- `handlers/setup/new_project_flow.py` - name input, git choice
- `keyboards/setup/git_choice.py` - git options keyboard
- `services/setup/git_operations.py` - git init, gh repo create

### Task 21-25: Launch & Rename
- `keyboards/setup/confirm.py` - rename confirm keyboard
- `services/setup/chat_rename.py` - rename_chat_safe() with retry
- `services/setup/project_setup.py` - atomic launch with rollback
- `handlers/setup/launch.py` - launch phase handler

### Task 26-28: Middleware & Integration
- `middleware/setup_blocker.py` - block non-setup commands
- Update main.py to register middleware
- Integration testing

### Task 29-30: E2E Testing
- Manual E2E tests via Telegram MCP
- Document test scenarios

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
