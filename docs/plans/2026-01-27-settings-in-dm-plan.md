# Settings in DM Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `/settings` command in DM to configure global defaults that new threads inherit.

**Architecture:** Two-level inheritance (Global → Thread). Global defaults stored in `config.json["global_defaults"]`. ThreadInfo fields become Optional — `None` means inherit from global.

**Tech Stack:** Python, aiogram, pydantic

---

## Task 1: Add HARDCODED_DEFAULTS and global defaults functions to config.py

**Files:**
- Modify: `src/codogram/config.py`
- Test: `tests/test_config_global_defaults.py`

**Step 1: Write the failing test**

Create `tests/test_config_global_defaults.py`:

```python
"""Tests for global defaults functionality."""
import json
import pytest
from pathlib import Path


def test_hardcoded_defaults_exists():
    """HARDCODED_DEFAULTS has all required keys."""
    from codogram.config import HARDCODED_DEFAULTS

    required_keys = [
        "auto_accept",
        "response_mode",
        "display_mode",
        "line_limit",
        "display_bullet",
        "display_thinking_text",
        "working_status",
        "feat_suggestions",
        "feat_avatar_pack",
    ]
    for key in required_keys:
        assert key in HARDCODED_DEFAULTS, f"Missing key: {key}"


def test_get_global_defaults_returns_hardcoded_when_no_config(tmp_path, monkeypatch):
    """get_global_defaults returns HARDCODED_DEFAULTS when no global_defaults in config."""
    from codogram import config
    from codogram.config import HARDCODED_DEFAULTS

    # Point config to temp directory
    config_path = tmp_path / "config.json"
    config_path.write_text('{"projects": {}}')
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    result = config.get_global_defaults()
    assert result == HARDCODED_DEFAULTS


def test_get_global_defaults_returns_saved_values(tmp_path, monkeypatch):
    """get_global_defaults returns values from config when present."""
    from codogram import config

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "projects": {},
        "global_defaults": {"auto_accept": True, "line_limit": 10}
    }))
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    result = config.get_global_defaults()
    assert result["auto_accept"] is True
    assert result["line_limit"] == 10


def test_set_global_default_creates_key(tmp_path, monkeypatch):
    """set_global_default creates global_defaults if missing."""
    from codogram import config

    config_dir = tmp_path
    config_path = tmp_path / "config.json"
    config_path.write_text('{"projects": {}}')
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    config.set_global_default("auto_accept", True)

    saved = json.loads(config_path.read_text())
    assert saved["global_defaults"]["auto_accept"] is True


def test_set_global_default_preserves_other_keys(tmp_path, monkeypatch):
    """set_global_default preserves existing keys."""
    from codogram import config

    config_dir = tmp_path
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "projects": {},
        "global_defaults": {"line_limit": 10}
    }))
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    config.set_global_default("auto_accept", True)

    saved = json.loads(config_path.read_text())
    assert saved["global_defaults"]["auto_accept"] is True
    assert saved["global_defaults"]["line_limit"] == 10
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_global_defaults.py -v`
Expected: FAIL with ImportError (HARDCODED_DEFAULTS not defined)

**Step 3: Write implementation**

Add to `src/codogram/config.py` after the imports:

```python
from typing import Any

# Hardcoded defaults - fallback when no global_defaults in config
HARDCODED_DEFAULTS: dict[str, Any] = {
    "auto_accept": False,
    "response_mode": "all",
    "display_mode": "lines",
    "line_limit": 5,
    "display_bullet": True,
    "display_thinking_text": False,
    "working_status": False,
    "feat_suggestions": False,
    "feat_avatar_pack": False,
}


def get_global_defaults() -> dict[str, Any]:
    """Load global defaults from config, falling back to HARDCODED_DEFAULTS."""
    config = load_config()
    saved = config.get("global_defaults", {})
    # Merge: saved values override hardcoded
    return {**HARDCODED_DEFAULTS, **saved}


def set_global_default(key: str, value: Any) -> None:
    """Update a single global default and save."""
    config = load_config()
    if "global_defaults" not in config:
        config["global_defaults"] = {}
    config["global_defaults"][key] = value
    save_config(config)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_global_defaults.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/config.py tests/test_config_global_defaults.py
git commit -m "feat(config): add global defaults functions"
```

---

## Task 2: Add get_thread_setting helper function

**Files:**
- Modify: `src/codogram/core/session_manager.py`
- Test: `tests/test_thread_setting.py`

**Step 1: Write the failing test**

Create `tests/test_thread_setting.py`:

```python
"""Tests for get_thread_setting helper."""
import pytest


def test_get_thread_setting_returns_thread_value_when_set():
    """Thread override takes precedence over global."""
    from codogram.core.session_manager import ThreadInfo, get_thread_setting

    thread = ThreadInfo(thread_id=None, name="test")
    thread.auto_accept = True  # Explicit override

    # Even if global is False, thread value wins
    result = get_thread_setting(thread, "auto_accept", {"auto_accept": False})
    assert result is True


def test_get_thread_setting_returns_global_when_thread_none():
    """Returns global default when thread value is None."""
    from codogram.core.session_manager import ThreadInfo, get_thread_setting

    thread = ThreadInfo(thread_id=None, name="test")
    thread.auto_accept = None  # Not set

    result = get_thread_setting(thread, "auto_accept", {"auto_accept": True})
    assert result is True


def test_get_thread_setting_handles_all_settings():
    """All setting keys work correctly."""
    from codogram.core.session_manager import ThreadInfo, get_thread_setting

    thread = ThreadInfo(thread_id=None, name="test")
    defaults = {
        "auto_accept": True,
        "response_mode": "polite",
        "display_mode": "headers",
        "line_limit": 10,
        "display_bullet": False,
        "display_thinking_text": True,
        "working_status": True,
    }

    for key, expected in defaults.items():
        result = get_thread_setting(thread, key, defaults)
        assert result == expected, f"Failed for {key}"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_thread_setting.py -v`
Expected: FAIL with ImportError (get_thread_setting not defined)

**Step 3: Write implementation**

Add to `src/codogram/core/session_manager.py` after imports:

```python
from typing import Any

def get_thread_setting(thread: 'ThreadInfo', key: str, global_defaults: dict[str, Any]) -> Any:
    """Get effective setting: thread override or global default.

    Args:
        thread: ThreadInfo instance
        key: Setting key (e.g. "auto_accept")
        global_defaults: Dict of global defaults

    Returns:
        Thread value if not None, otherwise global default
    """
    thread_value = getattr(thread, key, None)
    if thread_value is not None:
        return thread_value
    return global_defaults.get(key)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_thread_setting.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/core/session_manager.py tests/test_thread_setting.py
git commit -m "feat(session_manager): add get_thread_setting helper"
```

---

## Task 3: Make ThreadInfo settings fields Optional

**Files:**
- Modify: `src/codogram/core/session_manager.py`
- Test: `tests/test_thread_optional_fields.py`

**Step 1: Write the failing test**

Create `tests/test_thread_optional_fields.py`:

```python
"""Tests for ThreadInfo optional fields."""


def test_threadinfo_settings_default_to_none():
    """New ThreadInfo has None for all settings (inherits from global)."""
    from codogram.core.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=None, name="test")

    assert thread.auto_accept is None
    assert thread.response_mode is None
    assert thread.display_mode is None
    assert thread.line_limit is None
    assert thread.display_bullet is None
    assert thread.display_thinking_text is None
    assert thread.working_status is None


def test_threadinfo_accepts_explicit_values():
    """ThreadInfo can have explicit values set."""
    from codogram.core.session_manager import ThreadInfo

    thread = ThreadInfo(
        thread_id=None,
        name="test",
        auto_accept=True,
        display_mode="headers",
    )

    assert thread.auto_accept is True
    assert thread.display_mode == "headers"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_thread_optional_fields.py -v`
Expected: FAIL (auto_accept defaults to False, not None)

**Step 3: Write implementation**

Modify `ThreadInfo` in `src/codogram/core/session_manager.py`:

```python
@dataclass
class ThreadInfo:
    """State for a single thread (topic) within a project."""
    thread_id: int | None  # None = General topic
    name: str              # mystic, arcane, user-provided, or "main"
    topic_name: str | None = None  # Telegram topic name for debugging

    # Runtime state (from history.jsonl):
    session_id: str | None = None
    jsonl_path: str | None = None

    # Tasks:
    watcher_task: asyncio.Task | None = field(default=None, repr=False)
    poller_task: asyncio.Task | None = field(default=None, repr=False)
    binding_task: asyncio.Task | None = field(default=None, repr=False)
    launch_task: asyncio.Task | None = field(default=None, repr=False)

    # For session binding:
    last_sent_message: str | None = None
    awaiting_new_session: bool = False
    start_requested_at: float | None = None

    # Worktree support:
    worktree_path: str | None = None
    base_branch: str | None = None
    archived: bool = False

    # Settings - None means inherit from global defaults
    auto_accept: bool | None = None
    display_mode: str | None = None
    line_limit: int | None = None
    display_bullet: bool | None = None
    display_thinking_text: bool | None = None
    working_status: bool | None = None
    response_mode: str | None = None

    # Persisted message IDs (for cleanup after restart):
    last_suggestion_msg_id: int | None = None
    last_ask_msg_id: int | None = None
    last_permission_msg_id: int | None = None

    # Runtime-only (not persisted):
    notified_closed: bool = False
    thinking_needs_resend: bool = False

    # ... rest of methods unchanged
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_thread_optional_fields.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/core/session_manager.py tests/test_thread_optional_fields.py
git commit -m "refactor(session_manager): make ThreadInfo settings Optional"
```

---

## Task 4: Add strings for DM settings

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add strings**

Add to `src/codogram/strings.py`:

```python
# --- DM Settings ---

DM_SETTINGS_HEADER = "**Global defaults**"
DM_SETTINGS_HINT = "/reset\\_to\\_default — reset to factory defaults"

# Reset confirmation
RESET_THREAD_CONFIRM = "Reset this thread to global defaults?"
RESET_ALL_CONFIRM = "Reset ALL threads in ALL projects to global defaults?"
RESET_THREAD_DONE = "Thread reset to global defaults"
RESET_ALL_DONE = "All threads reset to global defaults"

# Settings footer in group
SETTINGS_RESET_HINT = "/reset\\_to\\_default — reset to global defaults"
```

**Step 2: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat(strings): add DM settings strings"
```

---

## Task 5: Add /settings command handler for DM

**Files:**
- Modify: `src/codogram/handlers/dm.py`
- Modify: `src/codogram/services/menu.py` (add /settings to DM_COMMANDS)

**Step 1: Update DM_COMMANDS in menu.py**

In `src/codogram/services/menu.py`, update DM_COMMANDS:

```python
DM_COMMANDS = [
    BotCommand(command="start", description="Start or show status"),
    BotCommand(command="settings", description="Global defaults"),
    BotCommand(command="dashboard", description="View all projects"),
    BotCommand(command="check_env", description="Check environment"),
    BotCommand(command="intro", description="Show intro again"),
]
```

**Step 2: Add handler in dm.py**

Add to `src/codogram/handlers/dm.py`:

```python
from ..config import get_global_defaults, set_global_default
from ..telegram.keyboards.settings import settings_keyboard_dm


def _build_dm_settings_text() -> str:
    """Build settings message text for DM (global defaults)."""
    defaults = get_global_defaults()

    auto_status = "● on" if defaults["auto_accept"] else "○ off"
    response_mode = defaults["response_mode"]

    if defaults["display_mode"] == "lines":
        verbose_status = f"lines ({defaults['line_limit']})"
    else:
        verbose_status = defaults["display_mode"]

    bullet_status = "● on" if defaults["display_bullet"] else "○ off"
    thinking_status = "● on" if defaults["display_thinking_text"] else "○ off"
    working_status = "● on" if defaults["working_status"] else "○ off"
    suggestions_status = "● on" if defaults["feat_suggestions"] else "○ off"
    avatar_pack_status = "● on" if defaults["feat_avatar_pack"] else "○ off"

    lines = [strings.DM_SETTINGS_HEADER, ""]
    lines.append("chat")
    lines.append(f"• /auto\\_accept: {auto_status}")
    lines.append(f"• /response\\_mode: {response_mode}")
    lines.append("")
    lines.append("ui")
    lines.append(f"• /verbose\\_mode: {verbose_status}")
    lines.append(f"• /display\\_bullet: {bullet_status}")
    lines.append(f"• /display\\_thinking\\_text: {thinking_status}")
    lines.append("")
    lines.append("experimental features")
    lines.append(f"• /working\\_status: {working_status}")
    lines.append(f"• /exp\\_suggestions: {suggestions_status}")
    lines.append(f"• /exp\\_avatar\\_pack: {avatar_pack_status}")
    lines.append("")
    lines.append(strings.DM_SETTINGS_HINT)

    return "\n".join(lines)


@router.message(Command("settings"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_settings(message: Message, telegram_queue: TelegramQueue):
    """Show global settings in DM."""
    if not is_admin(message):
        return

    text = _build_dm_settings_text()
    kb = settings_keyboard_dm(page=0)
    await telegram_queue.send(message.chat.id, text, reply_markup=kb)
```

**Step 3: Commit**

```bash
git add src/codogram/handlers/dm.py src/codogram/services/menu.py
git commit -m "feat(dm): add /settings command for global defaults"
```

---

## Task 6: Add settings_keyboard_dm function

**Files:**
- Modify: `src/codogram/telegram/keyboards/settings.py`

**Step 1: Add keyboard function**

Add to `src/codogram/telegram/keyboards/settings.py`:

```python
# Button groups for DM (no claude section)
SETTINGS_BUTTON_GROUPS_DM = [
    # Group 0: chat
    ["auto_accept", "response_mode"],
    # Group 1: ui
    ["verbose_mode", "display_bullet", "display_thinking_text"],
    # Group 2: experimental
    ["working_status", "exp_suggestions", "exp_avatar_pack"],
]


def settings_keyboard_dm(page: int = 0) -> InlineKeyboardMarkup:
    """Build paginated settings keyboard for DM (global defaults).

    Args:
        page: Current page (0-based)

    Returns:
        Inline keyboard with current group buttons + navigation
    """
    buttons = []

    # Clamp page to valid range
    page = max(0, min(page, len(SETTINGS_BUTTON_GROUPS_DM) - 1))

    # Get current group
    group = SETTINGS_BUTTON_GROUPS_DM[page]
    for cmd in group:
        action = _COMMAND_TO_ACTION.get(cmd, cmd)
        buttons.append([InlineKeyboardButton(
            text=f"/{cmd}",
            callback_data=f"dmset:{action}"
        )])

    # Navigation + Close row
    total_pages = len(SETTINGS_BUTTON_GROUPS_DM)
    nav_close_row = []

    if total_pages > 1 and page > 0:
        nav_close_row.append(InlineKeyboardButton(
            text="◀",
            callback_data=f"dmset:page:{page - 1}"
        ))
    elif total_pages > 1:
        nav_close_row.append(InlineKeyboardButton(
            text="•",
            callback_data="dmset:noop"
        ))

    nav_close_row.append(InlineKeyboardButton(
        text=strings.BTN_CLOSE,
        callback_data="dmset:close"
    ))

    if total_pages > 1 and page < total_pages - 1:
        nav_close_row.append(InlineKeyboardButton(
            text="▶",
            callback_data=f"dmset:page:{page + 1}"
        ))
    elif total_pages > 1:
        nav_close_row.append(InlineKeyboardButton(
            text="•",
            callback_data="dmset:noop"
        ))

    buttons.append(nav_close_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Step 2: Export from __init__.py**

Add to `src/codogram/telegram/keyboards/__init__.py`:

```python
from .settings import settings_keyboard, settings_keyboard_dm
```

**Step 3: Commit**

```bash
git add src/codogram/telegram/keyboards/settings.py src/codogram/telegram/keyboards/__init__.py
git commit -m "feat(keyboards): add settings_keyboard_dm for DM"
```

---

## Task 7: Add DM settings callback handlers

**Files:**
- Modify: `src/codogram/handlers/dm.py`

**Step 1: Add callback handlers**

Add to `src/codogram/handlers/dm.py`:

```python
from ..telegram.keyboards.settings import settings_keyboard_dm, SETTINGS_BUTTON_GROUPS_DM, _COMMAND_TO_ACTION


@router.callback_query(F.data == "dmset:noop")
async def callback_dm_settings_noop(callback: CallbackQuery):
    """Handle placeholder button press."""
    await callback.answer()


@router.callback_query(F.data == "dmset:close")
async def callback_dm_settings_close(callback: CallbackQuery):
    """Close DM settings message."""
    if callback.message:
        await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("dmset:page:"))
async def callback_dm_settings_page(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle DM settings page navigation."""
    try:
        new_page = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer("Invalid page")
        return

    text = _build_dm_settings_text()
    kb = settings_keyboard_dm(page=new_page)
    await telegram_queue.edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("dmset:"))
async def callback_dm_settings(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle DM settings button presses."""
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Invalid callback")
        return

    action = parts[1]
    defaults = get_global_defaults()

    # Map action to setting key
    action_to_key = {
        "aa": "auto_accept",
        "rm": "response_mode",
        "db": "display_bullet",
        "dt": "display_thinking_text",
        "ws": "working_status",
        "es": "feat_suggestions",
        "ea": "feat_avatar_pack",
    }

    if action == "v":
        # Verbose mode needs special handling - open menu
        # For now, cycle through modes
        modes = ["lines", "show_all", "headers", "current", "silence"]
        current = defaults["display_mode"]
        try:
            next_idx = (modes.index(current) + 1) % len(modes)
        except ValueError:
            next_idx = 0
        set_global_default("display_mode", modes[next_idx])
        await callback.answer(f"Mode: {modes[next_idx]}")
    elif action == "rm":
        # Cycle response mode
        modes = ["all", "polite", "mentions"]
        current = defaults["response_mode"]
        try:
            next_idx = (modes.index(current) + 1) % len(modes)
        except ValueError:
            next_idx = 0
        set_global_default("response_mode", modes[next_idx])
        await callback.answer(f"Response: {modes[next_idx]}")
    elif action in action_to_key:
        key = action_to_key[action]
        new_value = not defaults[key]
        set_global_default(key, new_value)
        status = "● on" if new_value else "○ off"

        labels = {
            "auto_accept": "Auto-accept",
            "display_bullet": "Bullet prefix",
            "display_thinking_text": "Thinking text",
            "working_status": "Working status",
            "feat_suggestions": "Suggestions",
            "feat_avatar_pack": "Avatar pack",
        }
        label = labels.get(key, key)
        await callback.answer(f"{label}: {status}")
    else:
        await callback.answer("Unknown action")
        return

    # Determine current page
    current_page = 0
    action_to_cmd = {v: k for k, v in _COMMAND_TO_ACTION.items()}
    if action in action_to_cmd:
        cmd = action_to_cmd[action]
        for i, group in enumerate(SETTINGS_BUTTON_GROUPS_DM):
            if cmd in group:
                current_page = i
                break

    # Update message
    text = _build_dm_settings_text()
    kb = settings_keyboard_dm(page=current_page)
    await telegram_queue.edit(callback.message, text, reply_markup=kb)
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/dm.py
git commit -m "feat(dm): add settings callback handlers"
```

---

## Task 8: Add /reset_to_default command

**Files:**
- Create: `src/codogram/handlers/settings/reset.py`
- Modify: `src/codogram/handlers/settings/__init__.py`

**Step 1: Create reset.py**

Create `src/codogram/handlers/settings/reset.py`:

```python
"""Reset to default command handler."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.enums import ChatType

from ...core.session_manager import project_manager
from ...telegram.queue import TelegramQueue
from ... import strings
from ...config import settings

router = Router(name="settings_reset")


def _is_admin(message: Message) -> bool:
    """Check if user is admin."""
    return message.from_user.id in settings.get_admin_ids()


def _reset_thread_to_defaults(thread) -> None:
    """Clear all setting overrides in thread."""
    thread.auto_accept = None
    thread.response_mode = None
    thread.display_mode = None
    thread.line_limit = None
    thread.display_bullet = None
    thread.display_thinking_text = None
    thread.working_status = None


def _reset_all_threads() -> int:
    """Reset all threads in all projects. Returns count of reset threads."""
    count = 0
    for project in project_manager.projects.values():
        for thread in project.threads.values():
            _reset_thread_to_defaults(thread)
            count += 1
    project_manager._save()
    return count


@router.message(Command("reset_to_default", ignore_case=True), F.chat.type == ChatType.PRIVATE)
async def cmd_reset_to_default_dm(message: Message, telegram_queue: TelegramQueue):
    """Reset all threads to global defaults (DM version)."""
    if not _is_admin(message):
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes", callback_data="reset:all:yes"),
            InlineKeyboardButton(text="No", callback_data="reset:all:no"),
        ]
    ])
    await telegram_queue.send(message.chat.id, strings.RESET_ALL_CONFIRM, reply_markup=kb)


@router.message(Command("reset_to_default", ignore_case=True))
async def cmd_reset_to_default(message: Message, telegram_queue: TelegramQueue):
    """Reset current thread to global defaults."""
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await telegram_queue.reply(message, "Thread not found.")
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes", callback_data=f"reset:thread:{thread_id}:yes"),
            InlineKeyboardButton(text="No", callback_data="reset:thread:no"),
        ]
    ])
    await telegram_queue.reply(message, strings.RESET_THREAD_CONFIRM, reply_markup=kb)


@router.callback_query(F.data == "reset:all:yes")
async def callback_reset_all_yes(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Confirm reset all threads."""
    count = _reset_all_threads()
    await telegram_queue.edit(callback.message, strings.RESET_ALL_DONE)
    await callback.answer(f"Reset {count} threads")


@router.callback_query(F.data == "reset:all:no")
async def callback_reset_all_no(callback: CallbackQuery):
    """Cancel reset all."""
    await callback.message.delete()
    await callback.answer("Cancelled")


@router.callback_query(F.data.startswith("reset:thread:") & F.data.endswith(":yes"))
async def callback_reset_thread_yes(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Confirm reset thread."""
    parts = callback.data.split(":")
    thread_id_str = parts[2]
    thread_id = None if thread_id_str == "None" else int(thread_id_str)

    chat_id = callback.message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Project not found")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await callback.answer("Thread not found")
        return

    _reset_thread_to_defaults(thread)
    project_manager._save()

    await telegram_queue.edit(callback.message, strings.RESET_THREAD_DONE)
    await callback.answer("Reset done")


@router.callback_query(F.data == "reset:thread:no")
async def callback_reset_thread_no(callback: CallbackQuery):
    """Cancel reset thread."""
    await callback.message.delete()
    await callback.answer("Cancelled")
```

**Step 2: Update __init__.py**

Update `src/codogram/handlers/settings/__init__.py`:

```python
from .main import router as main_router
from .verbose_menu import router as verbose_router
from .reset import router as reset_router

__all__ = ["main_router", "verbose_router", "reset_router"]
```

**Step 3: Register router in main.py**

Find where routers are included in `src/codogram/main.py` and add:

```python
from .handlers.settings import reset_router
# ...
dp.include_router(reset_router)
```

**Step 4: Commit**

```bash
git add src/codogram/handlers/settings/reset.py src/codogram/handlers/settings/__init__.py src/codogram/main.py
git commit -m "feat(settings): add /reset_to_default command"
```

---

## Task 9: Update _build_settings_text to use get_thread_setting

**Files:**
- Modify: `src/codogram/handlers/settings/main.py`

**Step 1: Update _build_settings_text**

Replace the settings reading logic in `_build_settings_text`:

```python
def _build_settings_text(project, thread, tmux_name: str) -> str:
    """Build settings message text. Used by cmd_settings and callback handler."""
    from ...tmux.session import TmuxSession
    from ...services.session_state import SessionStateService
    from ...core.session_manager import get_thread_setting
    from ...config import get_global_defaults

    global_defaults = get_global_defaults()

    # Get settings from thread with fallback to global
    if thread:
        auto_accept = get_thread_setting(thread, "auto_accept", global_defaults)
        display_mode = get_thread_setting(thread, "display_mode", global_defaults)
        line_limit = get_thread_setting(thread, "line_limit", global_defaults)
        display_bullet = get_thread_setting(thread, "display_bullet", global_defaults)
        display_thinking_text = get_thread_setting(thread, "display_thinking_text", global_defaults)
        working_status = get_thread_setting(thread, "working_status", global_defaults)
        response_mode = get_thread_setting(thread, "response_mode", global_defaults)
        context_name = thread.name
        cwd = thread.worktree_path or project.cwd
    else:
        # Fallback to project (legacy) or global
        auto_accept = project.auto_accept if project.auto_accept else global_defaults["auto_accept"]
        display_mode = project.display_mode if project.display_mode != "lines" else global_defaults["display_mode"]
        line_limit = project.line_limit if project.line_limit != 5 else global_defaults["line_limit"]
        display_bullet = project.display_bullet if not project.display_bullet else global_defaults["display_bullet"]
        display_thinking_text = project.display_thinking_text if not project.display_thinking_text else global_defaults["display_thinking_text"]
        working_status = project.working_status if project.working_status else global_defaults["working_status"]
        response_mode = project.response_mode if project.response_mode != "all" else global_defaults["response_mode"]
        context_name = project.project_name
        cwd = project.cwd

    # ... rest of the function unchanged, but add reset hint at the end

    # After experimental features section, add:
    lines.append("")
    lines.append(strings.SETTINGS_RESET_HINT)

    return "\n".join(lines)
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/settings/main.py
git commit -m "refactor(settings): use get_thread_setting with global defaults"
```

---

## Task 10: Update all toggle commands to use get_thread_setting

**Files:**
- Modify: `src/codogram/handlers/settings/main.py`

**Step 1: Update toggle commands**

Update each toggle command (cmd_auto_accept, cmd_display_bullet, etc.) to:
1. Get current value via `get_thread_setting`
2. Toggle and set explicitly on thread

Example for `cmd_auto_accept`:

```python
@router.message(Command("auto_accept", ignore_case=True))
async def cmd_auto_accept(message: Message, telegram_queue: TelegramQueue):
    """Toggle auto-accept."""
    from ...core.session_manager import get_thread_setting
    from ...config import get_global_defaults

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await telegram_queue.reply(message, "No project. Use /start first.")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await telegram_queue.reply(message, "Thread not found. Use /start first.")
        return

    global_defaults = get_global_defaults()
    current = get_thread_setting(thread, "auto_accept", global_defaults)
    thread.auto_accept = not current

    status = "● on" if thread.auto_accept else "○ off"
    project_manager._save()
    await telegram_queue.reply(message, f"Auto-accept: {status}")
```

Apply similar pattern to: `cmd_display_bullet`, `cmd_display_thinking_text`, `cmd_working_status`, `cmd_response_mode`.

**Step 2: Commit**

```bash
git add src/codogram/handlers/settings/main.py
git commit -m "refactor(settings): update toggle commands to use get_thread_setting"
```

---

## Task 11: Manual E2E testing

**Files:** None (testing only)

**Step 1: Start bot from worktree**

```bash
./kill-instance-and-start-from-worktree.sh
```

**Step 2: Test /settings in DM**

1. Send `/settings` in DM with bot
2. Verify shows "Global defaults" header
3. Verify no "claude" section
4. Click buttons, verify they toggle
5. Verify pagination works

**Step 3: Test /settings in group**

1. Send `/settings` in group
2. Verify shows reset hint at bottom
3. Verify effective values shown (inherited from global if not overridden)

**Step 4: Test /reset_to_default in group**

1. Toggle some settings in a thread
2. Send `/reset_to_default`
3. Confirm "Yes"
4. Send `/settings`, verify reset to global

**Step 5: Test /reset_to_default in DM**

1. Toggle some settings in multiple threads
2. Send `/reset_to_default` in DM
3. Confirm "Yes"
4. Check threads, verify all reset

**Step 6: Commit any fixes**

```bash
git add -A && git commit -m "fix: E2E testing fixes"
```

---

Plan complete and saved to `docs/plans/2026-01-27-settings-in-dm-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
