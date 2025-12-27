# Start Claude from Telegram Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable launching Claude sessions from Telegram via /start command instead of manual tmux setup

**Architecture:** Extend /start command to check for active session, resolve project path (convention ~/dev/{project} or saved), create tmux session with Claude if needed. Add conversation flow for directory creation and git setup via inline buttons.

**Tech Stack:** Python, aiogram (Telegram), asyncio, subprocess (tmux/git/gh)

---

## Task 1: Extend config to store project paths

**Files:**
- Modify: `src/codogram/session_manager.py`
- Modify: `src/codogram/config.py`

**Step 1: Update register_project to accept optional path**

In `session_manager.py`, change `register_project` method:

```python
def register_project(self, project_name: str, chat_id: int, path: str | None = None) -> None:
    """Register project -> chat mapping with optional custom path."""
    self.projects[project_name] = {
        "chat_id": chat_id,
        "path": path,  # None means use convention ~/dev/{project_name}
    }
    self._save()
```

**Step 2: Update get_chat_id to handle new structure**

```python
def get_chat_id(self, project_name: str) -> int | None:
    """Get chat_id for project."""
    project = self.projects.get(project_name)
    if project is None:
        return None
    # Handle both old format (int) and new format (dict)
    if isinstance(project, int):
        return project
    return project.get("chat_id")

def get_project_path(self, project_name: str) -> str | None:
    """Get custom path for project, or None for convention."""
    project = self.projects.get(project_name)
    if project is None or isinstance(project, int):
        return None
    return project.get("path")
```

**Step 3: Add get_project_by_chat method**

```python
def get_project_by_chat(self, chat_id: int) -> str | None:
    """Find project_name by chat_id."""
    for project_name, data in self.projects.items():
        if isinstance(data, int):
            if data == chat_id:
                return project_name
        elif data.get("chat_id") == chat_id:
            return project_name
    return None
```

**Step 4: Run existing tests**

Run: `cd agent-tools/codogram && source ~/dev/personal-agent/venv/bin/activate && python -m pytest tests/test_session_manager.py -v`

Expected: PASS (backwards compatible)

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(config): extend projects to store optional path"
```

---

## Task 2: Add project path resolver

**Files:**
- Create: `src/codogram/project_launcher.py`
- Create: `tests/test_project_launcher.py`

**Step 1: Write tests for path resolution**

```python
# tests/test_project_launcher.py
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from codogram.project_launcher import resolve_project_path, ProjectPathResult


def test_resolve_path_convention_exists(tmp_path):
    """Use convention path if directory exists."""
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()

    with patch("codogram.project_launcher.settings") as mock_settings:
        mock_settings.base_dir = str(tmp_path)
        result = resolve_project_path("my-project", None)

    assert result.exists
    assert result.path == str(project_dir)


def test_resolve_path_custom_exists(tmp_path):
    """Use custom path if provided and exists."""
    custom_dir = tmp_path / "custom" / "location"
    custom_dir.mkdir(parents=True)

    result = resolve_project_path("my-project", str(custom_dir))

    assert result.exists
    assert result.path == str(custom_dir)


def test_resolve_path_not_exists(tmp_path):
    """Return not exists if directory missing."""
    with patch("codogram.project_launcher.settings") as mock_settings:
        mock_settings.base_dir = str(tmp_path)
        result = resolve_project_path("nonexistent", None)

    assert not result.exists
    assert result.path == str(tmp_path / "nonexistent")
```

**Step 2: Run tests to verify they fail**

Run: `cd agent-tools/codogram && source ~/dev/personal-agent/venv/bin/activate && python -m pytest tests/test_project_launcher.py -v`

Expected: FAIL (module not found)

**Step 3: Implement project_launcher.py**

```python
# src/codogram/project_launcher.py
"""Project launcher - resolve paths and start Claude in tmux."""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import settings


@dataclass
class ProjectPathResult:
    path: str
    exists: bool


def resolve_project_path(project_name: str, custom_path: str | None) -> ProjectPathResult:
    """Resolve project path using custom path or convention."""
    if custom_path:
        path = Path(custom_path).expanduser()
    else:
        path = Path(settings.base_dir).expanduser() / project_name

    return ProjectPathResult(
        path=str(path),
        exists=path.is_dir(),
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd agent-tools/codogram && source ~/dev/personal-agent/venv/bin/activate && python -m pytest tests/test_project_launcher.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/project_launcher.py tests/test_project_launcher.py
git commit -m "feat(launcher): add project path resolver"
```

---

## Task 3: Add Claude launcher functions

**Files:**
- Modify: `src/codogram/project_launcher.py`
- Modify: `tests/test_project_launcher.py`

**Step 1: Add tests for Claude launcher**

```python
# Add to tests/test_project_launcher.py

from codogram.project_launcher import (
    is_tmux_session_exists,
    create_tmux_with_claude,
    LaunchResult,
)


def test_is_tmux_session_exists_false():
    """Return False for non-existent session."""
    result = is_tmux_session_exists("nonexistent-session-12345")
    assert result is False


def test_create_tmux_with_claude(tmp_path):
    """Create tmux session and run claude command."""
    session_name = f"test-claude-{os.getpid()}"
    project_path = str(tmp_path)

    try:
        result = create_tmux_with_claude(session_name, project_path)
        assert result.success
        assert is_tmux_session_exists(session_name)
    finally:
        # Cleanup
        subprocess.run(["tmux", "kill-session", "-t", session_name],
                      capture_output=True)
```

**Step 2: Run tests to verify they fail**

Run: `cd agent-tools/codogram && source ~/dev/personal-agent/venv/bin/activate && python -m pytest tests/test_project_launcher.py::test_is_tmux_session_exists_false -v`

Expected: FAIL (function not defined)

**Step 3: Implement launcher functions**

```python
# Add to src/codogram/project_launcher.py

@dataclass
class LaunchResult:
    success: bool
    error: str | None = None
    tmux_session: str | None = None


def is_tmux_session_exists(session_name: str) -> bool:
    """Check if tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
    )
    return result.returncode == 0


def create_tmux_with_claude(session_name: str, project_path: str) -> LaunchResult:
    """Create new tmux session and start Claude."""
    try:
        # Create detached tmux session in project directory
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-c", project_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LaunchResult(success=False, error=f"tmux error: {result.stderr}")

        # Send claude command
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "claude", "Enter"],
            capture_output=True,
        )

        return LaunchResult(success=True, tmux_session=session_name)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))
```

**Step 4: Run tests to verify they pass**

Run: `cd agent-tools/codogram && source ~/dev/personal-agent/venv/bin/activate && python -m pytest tests/test_project_launcher.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/project_launcher.py tests/test_project_launcher.py
git commit -m "feat(launcher): add tmux session creation with Claude"
```

---

## Task 4: Add git setup functions

**Files:**
- Modify: `src/codogram/project_launcher.py`

**Step 1: Add git/directory setup functions**

```python
# Add to src/codogram/project_launcher.py

def create_project_directory(path: str) -> LaunchResult:
    """Create project directory."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return LaunchResult(success=True)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))


def git_init(path: str) -> LaunchResult:
    """Initialize git repository."""
    try:
        result = subprocess.run(
            ["git", "init"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LaunchResult(success=False, error=result.stderr)
        return LaunchResult(success=True)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))


def git_init_with_github(path: str, private: bool = True) -> LaunchResult:
    """Initialize git and create GitHub repo."""
    try:
        # git init
        init_result = git_init(path)
        if not init_result.success:
            return init_result

        # gh repo create
        visibility = "--private" if private else "--public"
        result = subprocess.run(
            ["gh", "repo", "create", visibility, "--source", ".", "--push"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LaunchResult(success=False, error=f"gh error: {result.stderr}")
        return LaunchResult(success=True)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))


def git_clone(path: str, repo_url: str) -> LaunchResult:
    """Clone repository into path."""
    try:
        # Clone into current directory (path should be empty or not exist)
        parent = str(Path(path).parent)
        name = Path(path).name
        result = subprocess.run(
            ["git", "clone", repo_url, name],
            cwd=parent,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LaunchResult(success=False, error=f"git clone error: {result.stderr}")
        return LaunchResult(success=True)
    except Exception as e:
        return LaunchResult(success=False, error=str(e))
```

**Step 2: Commit**

```bash
git add src/codogram/project_launcher.py
git commit -m "feat(launcher): add git setup functions"
```

---

## Task 5: Add keyboard builders for conversation flow

**Files:**
- Create: `src/codogram/start_flow.py`

**Step 1: Create keyboard builders**

```python
# src/codogram/start_flow.py
"""Conversation flow for /start command."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def dir_not_found_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for when directory not found."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Создать", callback_data="start:create_dir"),
            InlineKeyboardButton(text="Указать другую", callback_data="start:custom_path"),
        ]
    ])


def git_setup_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for git setup options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="init локально", callback_data="start:git_init"),
            InlineKeyboardButton(text="init + gh create", callback_data="start:git_gh"),
        ],
        [
            InlineKeyboardButton(text="git clone", callback_data="start:git_clone"),
            InlineKeyboardButton(text="нет", callback_data="start:no_git"),
        ],
    ])


def git_visibility_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for GitHub repo visibility."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Private", callback_data="start:gh_private"),
            InlineKeyboardButton(text="Public", callback_data="start:gh_public"),
        ]
    ])
```

**Step 2: Commit**

```bash
git add src/codogram/start_flow.py
git commit -m "feat(start): add keyboard builders for conversation flow"
```

---

## Task 6: Implement /start handler with launch logic

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Add state storage for conversation flow**

```python
# Add at top of bot.py after imports
from .project_launcher import (
    resolve_project_path,
    is_tmux_session_exists,
    create_tmux_with_claude,
    create_project_directory,
    git_init,
    git_init_with_github,
    git_clone,
)
from .start_flow import (
    dir_not_found_keyboard,
    git_setup_keyboard,
    git_visibility_keyboard,
)

# Conversation state: chat_id -> {"state": str, "project": str, "path": str, ...}
_start_state: dict[int, dict] = {}
```

**Step 2: Rewrite cmd_start handler**

```python
@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id

    # Auto-register project by chat title
    project_name = message.chat.title
    if not project_name:
        await message.answer("Эта команда работает только в групповых чатах с названием проекта.")
        return

    # Register project if not exists
    existing_chat = manager.get_chat_id(project_name)
    if not existing_chat:
        manager.register_project(project_name, chat_id)

    # Check if Claude already running
    session = manager.get_session_by_chat(chat_id)
    if session and session.poller_task and not session.poller_task.done():
        tmux = TmuxSession(session.tmux_session, session.cwd)
        if is_tmux_session_exists(session.tmux_session):
            text = f"Claude активен.\nПроект: `{session.project_name}`\nПодключиться: `{tmux.attach_command()}`"
            try:
                await message.answer(text, parse_mode="Markdown")
            except Exception:
                await message.answer(text)
            return

    # Resolve project path
    custom_path = manager.get_project_path(project_name)
    path_result = resolve_project_path(project_name, custom_path)

    if not path_result.exists:
        # Directory doesn't exist - ask what to do
        _start_state[chat_id] = {
            "state": "awaiting_dir_choice",
            "project": project_name,
            "path": path_result.path,
        }
        await message.answer(
            f"Директория `{path_result.path}` не найдена.",
            reply_markup=dir_not_found_keyboard(),
            parse_mode="Markdown",
        )
        return

    # Directory exists - launch Claude
    await launch_claude(message, project_name, path_result.path)


async def launch_claude(message: Message, project_name: str, path: str):
    """Launch Claude in tmux session."""
    session_name = f"claude-{project_name}"

    # Check if session already exists
    if is_tmux_session_exists(session_name):
        # Kill old session
        import subprocess
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)

    result = create_tmux_with_claude(session_name, path)

    if result.success:
        await message.answer(
            f"Claude запущен в `{session_name}`\n"
            f"Подключиться: `tmux attach -t {session_name}`",
            parse_mode="Markdown",
        )
    else:
        await message.answer(f"Ошибка запуска: {result.error}")
```

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(start): implement /start with Claude launch"
```

---

## Task 7: Add callback handlers for conversation flow

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Add callback handlers**

```python
# Add after cmd_start

@router.callback_query(F.data == "start:create_dir")
async def on_start_create_dir(callback: CallbackQuery):
    """Handle create directory button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла, начни заново с /start")
        return

    # Create directory
    result = create_project_directory(state["path"])
    if not result.success:
        await callback.message.edit_text(f"Ошибка создания директории: {result.error}")
        await callback.answer()
        return

    # Ask about git
    state["state"] = "awaiting_git_choice"
    await callback.message.edit_text(
        f"Директория `{state['path']}` создана.\n\nНастроить гит?",
        reply_markup=git_setup_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "start:custom_path")
async def on_start_custom_path(callback: CallbackQuery):
    """Handle custom path button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла")
        return

    state["state"] = "awaiting_custom_path"
    await callback.message.edit_text("Отправь путь к директории проекта:")
    await callback.answer()


@router.callback_query(F.data == "start:git_init")
async def on_start_git_init(callback: CallbackQuery):
    """Handle git init button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла")
        return

    result = git_init(state["path"])
    if not result.success:
        await callback.message.edit_text(f"Ошибка git init: {result.error}")
    else:
        await callback.message.edit_text("Git инициализирован. Запускаю Claude...")
        await launch_claude(callback.message, state["project"], state["path"])

    _start_state.pop(chat_id, None)
    await callback.answer()


@router.callback_query(F.data == "start:git_gh")
async def on_start_git_gh(callback: CallbackQuery):
    """Handle git + gh button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла")
        return

    state["state"] = "awaiting_gh_visibility"
    await callback.message.edit_text(
        "Видимость репозитория?",
        reply_markup=git_visibility_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"start:gh_private", "start:gh_public"}))
async def on_start_gh_visibility(callback: CallbackQuery):
    """Handle GitHub visibility choice."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла")
        return

    private = callback.data == "start:gh_private"
    await callback.message.edit_text("Создаю репозиторий на GitHub...")

    result = git_init_with_github(state["path"], private=private)
    if not result.success:
        await callback.message.edit_text(f"Ошибка: {result.error}")
    else:
        await callback.message.edit_text("Репозиторий создан. Запускаю Claude...")
        await launch_claude(callback.message, state["project"], state["path"])

    _start_state.pop(chat_id, None)
    await callback.answer()


@router.callback_query(F.data == "start:git_clone")
async def on_start_git_clone(callback: CallbackQuery):
    """Handle git clone button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла")
        return

    state["state"] = "awaiting_clone_url"
    await callback.message.edit_text(
        "Отправь ссылку на репозиторий:\n"
        "• SSH: `git@github.com:user/repo.git`\n"
        "• HTTPS: `https://github.com/user/repo.git`",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "start:no_git")
async def on_start_no_git(callback: CallbackQuery):
    """Handle no git button."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    chat_id = callback.message.chat.id
    state = _start_state.get(chat_id)
    if not state:
        await callback.answer("Сессия истекла")
        return

    await callback.message.edit_text("Запускаю Claude...")
    await launch_claude(callback.message, state["project"], state["path"])

    _start_state.pop(chat_id, None)
    await callback.answer()
```

**Step 2: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(start): add callback handlers for conversation flow"
```

---

## Task 8: Handle text input for custom path and clone URL

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Update on_message handler**

```python
@router.message()
async def on_message(message: Message):
    if not is_admin(message.from_user.id):
        return

    if not message.text:
        return

    chat_id = message.chat.id

    # Check if we're in conversation flow
    state = _start_state.get(chat_id)
    if state:
        if state["state"] == "awaiting_custom_path":
            # User sent custom path
            path = message.text.strip()
            if not Path(path).expanduser().is_dir():
                await message.answer(f"Директория `{path}` не существует.", parse_mode="Markdown")
                return

            # Save path and launch
            manager.register_project(state["project"], chat_id, path=path)
            _start_state.pop(chat_id, None)
            await launch_claude(message, state["project"], str(Path(path).expanduser()))
            return

        elif state["state"] == "awaiting_clone_url":
            # User sent clone URL
            url = message.text.strip()
            await message.answer("Клонирую репозиторий...")

            result = git_clone(state["path"], url)
            if not result.success:
                await message.answer(f"Ошибка клонирования: {result.error}")
                return

            _start_state.pop(chat_id, None)
            await launch_claude(message, state["project"], state["path"])
            return

    # Normal message - send to tmux
    tmux = get_session_for_chat(chat_id)
    if tmux:
        tmux.send(message.text)
    else:
        if message.chat.id < 0:
            await message.answer("Нет активной сессии Claude. Используй /start для запуска.")
```

**Step 2: Add Path import at top**

```python
from pathlib import Path
```

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(start): handle text input for custom path and clone URL"
```

---

## Task 9: Remove /register_dir command

**Files:**
- Modify: `src/codogram/bot.py`
- Modify: `src/codogram/main.py`

**Step 1: Remove cmd_register_dir handler from bot.py**

Delete the entire `@router.message(Command("register_dir"))` handler.

**Step 2: Remove from bot commands in main.py**

```python
# Change this:
await bot.set_my_commands([
    BotCommand(command="start", description="Start bot / show status"),
    BotCommand(command="my_chat_id", description="Show your user ID"),
    BotCommand(command="register_dir", description="Register project for this chat"),
    BotCommand(command="esc", description="Send Escape to Claude"),
])

# To this:
await bot.set_my_commands([
    BotCommand(command="start", description="Start Claude / show status"),
    BotCommand(command="my_chat_id", description="Show your user ID"),
    BotCommand(command="esc", description="Send Escape to Claude"),
])
```

**Step 3: Commit**

```bash
git add src/codogram/bot.py src/codogram/main.py
git commit -m "refactor(start): remove /register_dir, functionality merged into /start"
```

---

## Task 10: Manual integration test

**Step 1: Restart bot**

```bash
pkill -f codogram
cd ~/dev/personal-agent/agent-tools/codogram && bash restart.sh
```

**Step 2: Test in Telegram**

1. Go to bz-merch-assistant chat
2. Send /start
3. Verify it asks about directory (if ~/dev/bz-merch-assistant doesn't exist)
4. Test "Создать" flow with git options
5. Verify Claude launches in tmux

**Step 3: Test existing project**

1. Go to personal-agent chat
2. Send /start
3. Verify it either shows status (if Claude running) or launches Claude

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(start): complete start-claude-from-telegram feature"
git push
```

---

## Task 11: Update design doc status

**Files:**
- Modify: `docs/designs/2025-12-25-start-claude-from-telegram.md`
- Modify: `docs/roadmap.md`

**Step 1: Update design status**

Change `**Status:** Ready for implementation` to `**Status:** Implemented`

**Step 2: Move to done in roadmap**

Move the feature from "В работе" to "Выполнено недавно"

**Step 3: Commit and push**

```bash
git add docs/
git commit -m "docs: mark start-claude-from-telegram as implemented"
git push
```
