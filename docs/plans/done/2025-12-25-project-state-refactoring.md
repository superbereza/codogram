# ProjectState Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor SessionState to ProjectState — единый источник правды с постепенным заполнением полей

**Architecture:** ProjectState хранит всё о проекте. Два входа (update_from_telegram, update_from_hook) заполняют поля и вызывают _maybe_start_tasks для запуска тасков когда все условия есть.

**Tech Stack:** Python, asyncio, aiogram, dataclasses

---

## Task 1: Create ProjectState dataclass

**Files:**
- Modify: `src/codogram/session_manager.py`
- Create: `tests/test_project_state.py`

**Step 1: Write test for ProjectState**

```python
# tests/test_project_state.py
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from codogram.session_manager import ProjectState


def test_project_state_defaults():
    """ProjectState has correct defaults."""
    project = ProjectState(project_name="test-project")

    assert project.project_name == "test-project"
    assert project.chat_id is None
    assert project.cwd is None
    assert project.tmux_session is None
    assert project.claude_session_id is None
    assert project.jsonl_path is None
    assert project.poller_task is None
    assert project.watcher_task is None


def test_project_state_with_values():
    """ProjectState accepts all values."""
    project = ProjectState(
        project_name="my-project",
        chat_id=-123,
        cwd="/home/user/dev/my-project",
        tmux_session="claude-my-project",
        claude_session_id="abc-123",
        jsonl_path="/path/to/jsonl",
    )

    assert project.chat_id == -123
    assert project.tmux_session == "claude-my-project"
    assert project.claude_session_id == "abc-123"
```

**Step 2: Run test to verify it fails**

Run: `cd agent-tools/codogram && python -m pytest tests/test_project_state.py -v`

Expected: FAIL (ProjectState not defined)

**Step 3: Add ProjectState dataclass**

Add to `src/codogram/session_manager.py` after imports:

```python
@dataclass
class ProjectState:
    """Всё что знаем о проекте. Поля заполняются постепенно."""
    project_name: str

    # Telegram (появляется при /start)
    chat_id: int | None = None

    # Filesystem
    cwd: str | None = None

    # Tmux (появляется при /start или hook)
    tmux_session: str | None = None
    poller_task: asyncio.Task | None = field(default=None, repr=False)

    # Claude (появляется при hook)
    claude_session_id: str | None = None
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = field(default=None, repr=False)
```

**Step 4: Run test to verify it passes**

Run: `cd agent-tools/codogram && python -m pytest tests/test_project_state.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py tests/test_project_state.py
git commit -m "feat(session): add ProjectState dataclass"
```

---

## Task 2: Create ProjectManager class

**Files:**
- Modify: `src/codogram/session_manager.py`
- Modify: `tests/test_project_state.py`

**Step 1: Write tests for ProjectManager**

Add to `tests/test_project_state.py`:

```python
from codogram.session_manager import ProjectManager


def test_project_manager_get_or_create():
    """get_or_create creates new project or returns existing."""
    pm = ProjectManager()

    # First call creates
    project1 = pm.get_or_create("test-project")
    assert project1.project_name == "test-project"

    # Second call returns same
    project2 = pm.get_or_create("test-project")
    assert project1 is project2


def test_project_manager_get_by_chat():
    """get_by_chat finds project by chat_id."""
    pm = ProjectManager()

    project = pm.get_or_create("test-project")
    project.chat_id = -123

    found = pm.get_by_chat(-123)
    assert found is project

    not_found = pm.get_by_chat(-999)
    assert not_found is None


def test_project_manager_get_by_session():
    """get_by_session finds project by claude_session_id."""
    pm = ProjectManager()

    project = pm.get_or_create("test-project")
    project.claude_session_id = "abc-123"

    found = pm.get_by_session("abc-123")
    assert found is project

    not_found = pm.get_by_session("xyz")
    assert not_found is None
```

**Step 2: Run tests to verify they fail**

Run: `cd agent-tools/codogram && python -m pytest tests/test_project_state.py -v`

Expected: FAIL (ProjectManager not defined)

**Step 3: Add ProjectManager class**

Add to `src/codogram/session_manager.py`:

```python
class ProjectManager:
    """Manages ProjectState instances."""

    def __init__(self):
        self.projects: dict[str, ProjectState] = {}  # by project_name
        self._config = load_config()
        self._load_projects()

    def _load_projects(self) -> None:
        """Load projects from config."""
        saved_projects = self._config.get("projects", {})
        for project_name, data in saved_projects.items():
            project = ProjectState(project_name=project_name)
            if isinstance(data, int):
                # Old format: just chat_id
                project.chat_id = data
            else:
                # New format: dict with chat_id and cwd
                project.chat_id = data.get("chat_id")
                project.cwd = data.get("cwd")
            self.projects[project_name] = project

    def _save(self) -> None:
        """Persist to disk."""
        # Projects (permanent)
        self._config["projects"] = {
            name: {"chat_id": p.chat_id, "cwd": p.cwd}
            for name, p in self.projects.items()
            if p.chat_id is not None
        }
        # Sessions (temporary)
        self._config["sessions"] = {
            name: {
                "tmux_session": p.tmux_session,
                "claude_session_id": p.claude_session_id,
                "jsonl_path": p.jsonl_path,
            }
            for name, p in self.projects.items()
            if p.claude_session_id is not None
        }
        save_config(self._config)

    def get_or_create(self, project_name: str) -> ProjectState:
        """Get existing project or create new one."""
        if project_name not in self.projects:
            self.projects[project_name] = ProjectState(project_name=project_name)
        return self.projects[project_name]

    def get_by_chat(self, chat_id: int) -> ProjectState | None:
        """Find project by chat_id."""
        for project in self.projects.values():
            if project.chat_id == chat_id:
                return project
        return None

    def get_by_session(self, session_id: str) -> ProjectState | None:
        """Find project by claude_session_id."""
        for project in self.projects.values():
            if project.claude_session_id == session_id:
                return project
        return None

    def get_by_tmux(self, tmux_session: str) -> ProjectState | None:
        """Find project by tmux_session."""
        for project in self.projects.values():
            if project.tmux_session == tmux_session:
                return project
        return None
```

**Step 4: Run tests**

Run: `cd agent-tools/codogram && python -m pytest tests/test_project_state.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py tests/test_project_state.py
git commit -m "feat(session): add ProjectManager class"
```

---

## Task 3: Add update_from_telegram and _maybe_start_tasks

**Files:**
- Modify: `src/codogram/session_manager.py`
- Modify: `tests/test_project_state.py`

**Step 1: Write test for update_from_telegram**

Add to `tests/test_project_state.py`:

```python
import asyncio
from unittest.mock import AsyncMock


def test_update_from_telegram():
    """update_from_telegram sets chat_id and cwd."""
    pm = ProjectManager()

    async def run():
        project = await pm.update_from_telegram(
            project_name="test-project",
            chat_id=-123,
            cwd="/home/user/dev/test-project",
            start_poller=AsyncMock(return_value=asyncio.current_task()),
            start_watcher=AsyncMock(return_value=asyncio.current_task()),
        )
        assert project.chat_id == -123
        assert project.cwd == "/home/user/dev/test-project"

    asyncio.run(run())


def test_maybe_start_tasks_needs_both():
    """_maybe_start_tasks needs tmux_session AND chat_id for poller."""
    pm = ProjectManager()

    async def run():
        mock_poller = AsyncMock(return_value=asyncio.current_task())
        mock_watcher = AsyncMock(return_value=asyncio.current_task())

        # Only chat_id - no poller
        project = pm.get_or_create("test")
        project.chat_id = -123
        await pm._maybe_start_tasks(project, mock_poller, mock_watcher)
        mock_poller.assert_not_called()

        # Add tmux_session - poller starts
        project.tmux_session = "claude-test"
        await pm._maybe_start_tasks(project, mock_poller, mock_watcher)
        mock_poller.assert_called_once()

    asyncio.run(run())
```

**Step 2: Run tests to verify they fail**

Expected: FAIL (update_from_telegram not defined)

**Step 3: Add methods to ProjectManager**

```python
    async def update_from_telegram(
        self,
        project_name: str,
        chat_id: int,
        cwd: str | None,
        start_poller,
        start_watcher,
    ) -> ProjectState:
        """Update project from /start command."""
        project = self.get_or_create(project_name)
        project.chat_id = chat_id
        if cwd:
            project.cwd = cwd

        await self._maybe_start_tasks(project, start_poller, start_watcher)
        self._save()
        return project

    async def _maybe_start_tasks(self, project: ProjectState, start_poller, start_watcher) -> None:
        """Start tasks if all required data is present."""
        # Poller: needs tmux_session + chat_id
        if project.tmux_session and project.chat_id:
            if not project.poller_task or project.poller_task.done():
                project.poller_task = await start_poller(project)

        # Watcher: needs jsonl_path + chat_id
        if project.jsonl_path and project.chat_id:
            if not project.watcher_task or project.watcher_task.done():
                project.watcher_task = await start_watcher(project)
```

**Step 4: Run tests**

Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py tests/test_project_state.py
git commit -m "feat(session): add update_from_telegram and _maybe_start_tasks"
```

---

## Task 4: Add update_from_hook

**Files:**
- Modify: `src/codogram/session_manager.py`
- Modify: `tests/test_project_state.py`

**Step 1: Write test**

```python
def test_update_from_hook():
    """update_from_hook sets Claude-related fields."""
    pm = ProjectManager()

    async def run():
        project = await pm.update_from_hook(
            session_id="abc-123",
            cwd="/home/user/dev/test-project",
            tmux_session="claude-test-project",
            start_poller=AsyncMock(return_value=asyncio.current_task()),
            start_watcher=AsyncMock(return_value=asyncio.current_task()),
        )

        assert project.project_name == "test-project"
        assert project.claude_session_id == "abc-123"
        assert project.tmux_session == "claude-test-project"
        assert project.cwd == "/home/user/dev/test-project"

    asyncio.run(run())
```

**Step 2: Add update_from_hook to ProjectManager**

```python
    async def update_from_hook(
        self,
        session_id: str,
        cwd: str,
        tmux_session: str,
        start_poller,
        start_watcher,
    ) -> ProjectState:
        """Update project from Claude hook."""
        project_name = get_project_name(Path(cwd))
        project = self.get_or_create(project_name)

        # Clear old session if different (prevents race with /new)
        if project.claude_session_id and project.claude_session_id != session_id:
            await self._stop_tasks(project)

        project.cwd = cwd
        project.tmux_session = tmux_session
        project.claude_session_id = session_id
        project.jsonl_path = self._find_jsonl(cwd, session_id)

        await self._maybe_start_tasks(project, start_poller, start_watcher)
        self._save()
        return project

    def _find_jsonl(self, cwd: str, session_id: str) -> str | None:
        """Find jsonl file for session."""
        project_hash = cwd.replace("/", "-")
        projects_dir = Path.home() / ".claude" / "projects" / project_hash

        if not projects_dir.exists():
            return None

        # Try exact match first
        exact = projects_dir / f"{session_id}.jsonl"
        if exact.exists():
            return str(exact)

        # Fallback to most recent
        jsonl_files = sorted(projects_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if jsonl_files:
            return str(jsonl_files[-1])

        return None

    async def _stop_tasks(self, project: ProjectState) -> None:
        """Stop running tasks."""
        if project.poller_task:
            project.poller_task.cancel()
            try:
                await project.poller_task
            except asyncio.CancelledError:
                pass
            project.poller_task = None

        if project.watcher_task:
            project.watcher_task.cancel()
            try:
                await project.watcher_task
            except asyncio.CancelledError:
                pass
            project.watcher_task = None
```

**Step 3: Run tests**

Expected: PASS

**Step 4: Commit**

```bash
git add src/codogram/session_manager.py tests/test_project_state.py
git commit -m "feat(session): add update_from_hook"
```

---

## Task 5: Add handle_session_end with race protection

**Files:**
- Modify: `src/codogram/session_manager.py`
- Modify: `tests/test_project_state.py`

**Step 1: Write test for race protection**

```python
def test_session_end_race_protection():
    """SessionEnd with old session_id is ignored."""
    pm = ProjectManager()

    async def run():
        mock_poller = AsyncMock(return_value=asyncio.current_task())
        mock_watcher = AsyncMock(return_value=asyncio.current_task())

        # Create project with session abc
        project = await pm.update_from_hook(
            session_id="abc",
            cwd="/tmp/test",
            tmux_session="test",
            start_poller=mock_poller,
            start_watcher=mock_watcher,
        )

        # Update to session xyz
        project.claude_session_id = "xyz"

        # SessionEnd for old "abc" should be ignored
        await pm.handle_session_end("abc")

        # Session still has xyz
        assert project.claude_session_id == "xyz"

    asyncio.run(run())
```

**Step 2: Add handle_session_end**

```python
    async def handle_session_end(self, session_id: str) -> None:
        """Handle Claude session end."""
        project = self.get_by_session(session_id)
        if not project:
            return

        # Race condition protection: ignore if session_id changed
        if project.claude_session_id != session_id:
            return

        # Clear Claude-related fields
        project.claude_session_id = None
        project.jsonl_path = None

        # Stop tasks
        await self._stop_tasks(project)

        # Keep: chat_id, cwd, tmux_session
        self._save()
```

**Step 3: Run tests**

Expected: PASS

**Step 4: Commit**

```bash
git add src/codogram/session_manager.py tests/test_project_state.py
git commit -m "feat(session): add handle_session_end with race protection"
```

---

## Task 6: Add restore_projects

**Files:**
- Modify: `src/codogram/session_manager.py`

**Step 1: Add restore_projects method**

```python
    async def restore_projects(self, start_poller, start_watcher) -> None:
        """Restore sessions from config after bot restart."""
        saved_sessions = self._config.get("sessions", {})

        for project_name, data in saved_sessions.items():
            project = self.get_or_create(project_name)

            tmux_session = data.get("tmux_session")
            if not tmux_session:
                continue

            # Check if tmux is alive
            from .tmux import TmuxSession
            tmux = TmuxSession(tmux_session, project.cwd or "/tmp")
            if not tmux.exists():
                continue

            # Restore session data
            project.tmux_session = tmux_session
            project.claude_session_id = data.get("claude_session_id")
            project.jsonl_path = data.get("jsonl_path")

            # Verify jsonl exists
            if project.jsonl_path and not Path(project.jsonl_path).exists():
                project.jsonl_path = None

            await self._maybe_start_tasks(project, start_poller, start_watcher)

        self._save()
```

**Step 2: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(session): add restore_projects"
```

---

## Task 7: Create project_manager instance

**Files:**
- Modify: `src/codogram/session_manager.py`

**Step 1: Add instance at end of file**

Replace `manager = SessionManager()` with:

```python
# Keep old manager for backwards compatibility during migration
manager = SessionManager()

# New project manager
project_manager = ProjectManager()
```

**Step 2: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(session): add project_manager instance"
```

---

## Task 8: Update main.py to use ProjectManager

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Update handle_register**

```python
from .session_manager import project_manager, ProjectState

async def handle_register(request: web.Request) -> web.Response:
    """Handle session registration from Claude hook."""
    data = await request.json()
    session_id = data.get("session_id")
    cwd = data.get("cwd")
    tmux_session = data.get("tmux_session")

    if not session_id or not cwd:
        return web.json_response({"error": "missing fields"}, status=400)

    bot = request.app["bot"]

    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project)

    async def start_watcher(project: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project)

    project = await project_manager.update_from_hook(
        session_id=session_id,
        cwd=cwd,
        tmux_session=tmux_session or "unknown",
        start_poller=start_poller,
        start_watcher=start_watcher,
    )

    return web.json_response({
        "status": "registered",
        "project": project.project_name,
        "has_chat": project.chat_id is not None,
    })
```

**Step 2: Update handle_unregister**

```python
async def handle_unregister(request: web.Request) -> web.Response:
    """Handle session unregistration from Claude hook."""
    data = await request.json()
    session_id = data.get("session_id")

    if not session_id:
        return web.json_response({"error": "missing session_id"}, status=400)

    await project_manager.handle_session_end(session_id)
    return web.json_response({"status": "unregistered"})
```

**Step 3: Update main() to use restore_projects**

In `async def main()`:

```python
    # Restore sessions
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project)

    async def start_watcher(project: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project)

    await project_manager.restore_projects(start_poller, start_watcher)
```

**Step 4: Commit**

```bash
git add src/codogram/main.py
git commit -m "refactor(main): use ProjectManager for hooks"
```

---

## Task 9: Update permission_poller to use ProjectState

**Files:**
- Modify: `src/codogram/permission_poller.py`

**Step 1: Update imports and function signature**

Change `SessionState` to `ProjectState`:

```python
from .session_manager import ProjectState

async def create_poller_task(bot: Bot, project: ProjectState) -> asyncio.Task:
    """Create permission poller task for project."""
    return asyncio.create_task(permission_poller_for_project(bot, project))


async def permission_poller_for_project(bot: Bot, project: ProjectState):
    """Background poller for permission prompts."""
    log("Poller started")

    tmux = TmuxSession(project.tmux_session, project.cwd or "/tmp")
    chat_id = project.chat_id

    # ... rest of the function stays the same
```

**Step 2: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "refactor(poller): use ProjectState"
```

---

## Task 10: Update watcher to use ProjectState

**Files:**
- Modify: `src/codogram/watcher.py`

**Step 1: Update imports and function signature**

Change `SessionState` to `ProjectState`:

```python
from .session_manager import ProjectState

async def create_watcher_task(bot: Bot, project: ProjectState) -> asyncio.Task:
    """Create watcher task for project."""
    return asyncio.create_task(watch_jsonl(bot, project))


async def watch_jsonl(bot: Bot, project: ProjectState):
    # Use project.jsonl_path, project.chat_id, etc.
```

**Step 2: Commit**

```bash
git add src/codogram/watcher.py
git commit -m "refactor(watcher): use ProjectState"
```

---

## Task 11: Update bot.py cmd_start

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Update imports**

```python
from .session_manager import project_manager, ProjectState
from .project_launcher import is_tmux_session_exists, create_tmux_with_claude
```

**Step 2: Rewrite cmd_start**

```python
@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    project_name = message.chat.title

    if not project_name:
        await message.answer("Эта команда работает только в групповых чатах с названием проекта.")
        return

    # Get or create project
    project = project_manager.get_or_create(project_name)
    project.chat_id = chat_id

    # Define task starters
    bot = message.bot
    async def start_poller(p: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p)

    # Case 1: Claude already running - connect
    if project.claude_session_id:
        await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
        project_manager._save()
        tmux = TmuxSession(project.tmux_session, project.cwd or "/tmp")
        await message.answer(
            f"Claude активен в `{project.tmux_session}`\n"
            f"Подключиться: `{tmux.attach_command()}`",
            parse_mode="Markdown",
        )
        return

    # Resolve path
    custom_path = project.cwd
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
    project.cwd = path_result.path
    await launch_claude_new(message, project, start_poller, start_watcher)


async def launch_claude_new(message: Message, project: ProjectState, start_poller, start_watcher):
    """Launch Claude in tmux session using new ProjectState."""
    import subprocess

    convention = f"claude-{project.project_name}"

    # Case 2: Our tmux exists - reuse
    if project.tmux_session == convention and is_tmux_session_exists(convention):
        subprocess.run(["tmux", "send-keys", "-t", convention, "claude", "Enter"], capture_output=True)
    # Case 3: Foreign tmux - create new alongside
    elif project.tmux_session and project.tmux_session != convention and is_tmux_session_exists(project.tmux_session):
        create_tmux_with_claude(convention, project.cwd)
        project.tmux_session = convention
    # Case 4: No tmux - create
    else:
        create_tmux_with_claude(convention, project.cwd)
        project.tmux_session = convention

    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    await message.answer(
        f"Claude запущен в `{project.tmux_session}`\n"
        f"Подключиться: `tmux attach -t {project.tmux_session}`\n\n"
        f"⏳ Ожидаю регистрацию...",
        parse_mode="Markdown",
    )
```

**Step 3: Update get_session_for_chat**

```python
def get_session_for_chat(chat_id: int) -> TmuxSession | None:
    """Get TmuxSession for chat_id."""
    project = project_manager.get_by_chat(chat_id)
    if project and project.tmux_session:
        return TmuxSession(project.tmux_session, project.cwd or "/tmp")
    return None
```

**Step 4: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): use ProjectManager in /start"
```

---

## Task 12: Add /restart_session command

**Files:**
- Modify: `src/codogram/bot.py`
- Modify: `src/codogram/start_flow.py`
- Modify: `src/codogram/main.py`

**Step 1: Add keyboard to start_flow.py**

```python
def restart_confirm_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for restart confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, перезапустить", callback_data="restart:confirm"),
            InlineKeyboardButton(text="Отмена", callback_data="restart:cancel"),
        ]
    ])
```

**Step 2: Add command handler to bot.py**

```python
@router.message(Command("restart_session"))
async def cmd_restart_session(message: Message):
    if not is_admin(message.from_user.id):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project or not project.tmux_session:
        await message.answer("Нет активной сессии для перезапуска.")
        return

    await message.answer(
        f"Перезапустить сессию `{project.tmux_session}`?",
        reply_markup=restart_confirm_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "restart:confirm")
async def on_restart_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await callback.answer("Сессия не найдена")
        return

    # Stop tasks
    await project_manager._stop_tasks(project)

    # Kill tmux if exists
    if project.tmux_session and is_tmux_session_exists(project.tmux_session):
        import subprocess
        subprocess.run(["tmux", "kill-session", "-t", project.tmux_session], capture_output=True)

    # Clear session data
    project.claude_session_id = None
    project.jsonl_path = None
    project.tmux_session = None

    await callback.message.edit_text("Сессия остановлена. Используй /start для запуска.")
    await callback.answer()


@router.callback_query(F.data == "restart:cancel")
async def on_restart_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Отменено.")
    await callback.answer()
```

**Step 3: Add command to main.py**

```python
await bot.set_my_commands([
    BotCommand(command="start", description="Start Claude / show status"),
    BotCommand(command="restart_session", description="Restart Claude session"),
    BotCommand(command="my_chat_id", description="Show your user ID"),
    BotCommand(command="esc", description="Send Escape to Claude"),
])
```

**Step 4: Commit**

```bash
git add src/codogram/bot.py src/codogram/start_flow.py src/codogram/main.py
git commit -m "feat(bot): add /restart_session command"
```

---

## Task 13: Remove old SessionManager usage

**Files:**
- Modify: `src/codogram/session_manager.py`
- Modify: `src/codogram/bot.py`

**Step 1: Remove old SessionManager class**

Keep only ProjectState, ProjectManager, and project_manager instance.

**Step 2: Update remaining references in bot.py**

Remove all `manager.` usages, use `project_manager.` instead.

**Step 3: Commit**

```bash
git add src/codogram/session_manager.py src/codogram/bot.py
git commit -m "refactor(session): remove old SessionManager"
```

---

## Task 14: Integration test

**Step 1: Restart bot**

```bash
pkill -f codogram
./agent-tools/codogram/restart.sh
```

**Step 2: Test scenarios**

1. `/start` in new chat → should ask about directory
2. Create directory → git options → Claude launches
3. `/start` when Claude running → shows status
4. Close Claude (/quit) → `/start` → Claude relaunches
5. `/restart_session` → confirms → restarts

**Step 3: Check logs**

```bash
tail -f ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(session): complete ProjectState refactoring"
git push
```

---

## Task 15: Update docs

**Files:**
- Modify: `docs/designs/2025-12-25-project-state-refactoring.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/ONBOARDING.md`

**Step 1: Update design status**

Change `**Status:** Ready for implementation` to `**Status:** Implemented`

**Step 2: Move to done in roadmap**

**Step 3: Update ONBOARDING.md with new architecture**

**Step 4: Commit and push**

```bash
git add docs/
git commit -m "docs: update after ProjectState refactoring"
git push
```

---

## Post-Implementation Fixes

### Ошибка 1: Case 3 в launch_claude_new

**Проблема в плане:** Task 11 описывал Case 3 как "Foreign tmux - create new alongside". Но "foreign" интерпретировалось как "не по конвенции `claude-{name}`", хотя на самом деле это мог быть наш tmux с другим именем (например `personal-agent` вместо `claude-personal-agent`).

**Последствие:** При /start в чате создавался новый tmux вместо подключения к существующему.

**Фикс:** Добавлен Case 2 в cmd_start который проверяет существующий tmux ДО вызова launch_claude_new.

### Ошибка 2: project.session_id в watcher.py

**Проблема:** Subagent при рефакторинге Task 10 заменил `session.session_id` на `project.session_id`, но в ProjectState поле называется `claude_session_id`.

**Фикс:** Заменено на `project.project_name`.

### Ошибка 3: jsonl_path не находился при restore

**Проблема:** `_find_jsonl` вызывается в update_from_hook, но если файл ещё не существует в момент hook (Claude создаёт jsonl не сразу), jsonl_path остаётся null. При restore он не пытался найти jsonl заново.

**Фикс:** Добавлена попытка найти jsonl при restore если его нет в конфиге.

### Урок

При subagent-driven development нужно ревьюить:
1. План — особенно edge cases и интерпретацию терминов
2. Реализацию — полнота замены ссылок при рефакторинге
