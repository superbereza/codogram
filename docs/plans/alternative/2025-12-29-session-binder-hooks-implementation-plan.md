# Session Binder Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix thread session mixup bug by implementing hook-based session binding with content matching fallback.

**Architecture:** HookServer receives Claude SessionStart hooks with exact tmux↔session mapping. SessionBinderService handles binding via hooks (primary) or content matching (fallback for sessions without hooks).

**Tech Stack:** Python 3.11+, aiohttp (HTTP server), aiogram (Telegram), pytest

---

## Task 1: Add hooks_enabled and hook_server_port to Settings

**Files:**
- Modify: `src/codogram/config.py:6-18`
- Test: `tests/test_config.py` (new file)

**Step 1: Write failing test**

Create `tests/test_config.py`:

```python
# tests/test_config.py
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest


def test_hooks_enabled_default_true():
    """hooks_enabled defaults to True."""
    from codogram.config import Settings
    s = Settings()
    assert s.hooks_enabled is True


def test_hooks_enabled_from_env():
    """hooks_enabled reads from HOOKS_ENABLED env."""
    os.environ["HOOKS_ENABLED"] = "false"
    from importlib import reload
    import codogram.config
    reload(codogram.config)
    from codogram.config import Settings
    s = Settings()
    assert s.hooks_enabled is False
    # Cleanup
    del os.environ["HOOKS_ENABLED"]


def test_hook_server_port_default():
    """hook_server_port defaults to 8787."""
    from codogram.config import Settings
    s = Settings()
    assert s.hook_server_port == 8787
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with "Settings has no attribute 'hooks_enabled'"

**Step 3: Implement config changes**

Modify `src/codogram/config.py`:

```python
# src/codogram/config.py
import json
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_token: str
    admin_ids: str  # Comma-separated list of admin user IDs
    base_dir: str  # e.g. /home/user/dev

    # Hooks configuration
    hooks_enabled: bool = True
    hook_server_port: int = 8787

    class Config:
        env_file = ".env"

    def get_admin_ids(self) -> set[int]:
        """Parse admin_ids string into set of ints."""
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}

settings = Settings()

# Config file path
CONFIG_PATH = Path(__file__).parent.parent.parent / ".config.json"

def load_config() -> dict:
    """Load .config.json or return default."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"projects": {}}

def save_config(config: dict) -> None:
    """Save config to .config.json."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_hooks_enabled_default_true -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/config.py tests/test_config.py
git commit -m "feat(config): add hooks_enabled and hook_server_port settings"
```

---

## Task 2: Create adapters directory structure

**Files:**
- Create: `src/codogram/adapters/__init__.py`

**Step 1: Create adapters package**

```python
# src/codogram/adapters/__init__.py
"""Adapters for external systems (HTTP, tmux, etc.)."""
```

**Step 2: Verify import works**

Run: `python -c "from codogram.adapters import *; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/adapters/__init__.py
git commit -m "feat: create adapters package"
```

---

## Task 3: Implement HookServer adapter

**Files:**
- Create: `src/codogram/adapters/hook_server.py`
- Test: `tests/test_hook_server.py`

**Step 1: Write failing test**

Create `tests/test_hook_server.py`:

```python
# tests/test_hook_server.py
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
import aiohttp


@pytest.mark.asyncio
async def test_hook_server_receives_session_start():
    """HookServer receives POST and calls callback."""
    from codogram.adapters.hook_server import HookServer

    received = []

    async def on_hook(session_id, cwd, tmux_session):
        received.append((session_id, cwd, tmux_session))

    server = HookServer(port=18787, on_session_hook=on_hook)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:18787/hook/session-start",
                json={
                    "session_id": "abc123",
                    "cwd": "/test/path",
                    "tmux_session": "claude-test"
                }
            ) as resp:
                assert resp.status == 200
                text = await resp.text()
                assert text == "ok"

        assert len(received) == 1
        assert received[0] == ("abc123", "/test/path", "claude-test")
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_hook_server_rejects_missing_session_id():
    """HookServer returns 400 for missing session_id."""
    from codogram.adapters.hook_server import HookServer

    async def on_hook(session_id, cwd, tmux_session):
        pass

    server = HookServer(port=18788, on_session_hook=on_hook)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:18788/hook/session-start",
                json={"cwd": "/test"}
            ) as resp:
                assert resp.status == 400
    finally:
        await server.stop()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_hook_server.py -v`
Expected: FAIL with "No module named 'codogram.adapters.hook_server'"

**Step 3: Implement HookServer**

Create `src/codogram/adapters/hook_server.py`:

```python
"""HTTP server for receiving Claude session hooks."""

from aiohttp import web

from ..logging_config import logger


class HookServer:
    """Receives SessionStart hooks from Claude."""

    def __init__(self, port: int, on_session_hook):
        self.port = port
        self.on_session_hook = on_session_hook
        self._app = None
        self._runner = None

    async def start(self):
        """Start the HTTP server."""
        self._app = web.Application()
        self._app.router.add_post('/hook/session-start', self._handle_session_start)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, '127.0.0.1', self.port)
        await site.start()

        logger.info(f"hook_server_started: port={self.port}")

    async def stop(self):
        """Stop the HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("hook_server_stopped")

    async def _handle_session_start(self, request: web.Request) -> web.Response:
        """Handle SessionStart hook from Claude."""
        try:
            data = await request.json()

            session_id = data.get('session_id')
            cwd = data.get('cwd')
            tmux_session = data.get('tmux_session')

            if not session_id:
                logger.warning("hook_missing_session_id")
                return web.Response(text='missing session_id', status=400)

            logger.info(f"hook_received: session={session_id[:8]}, tmux={tmux_session}, cwd={cwd}")

            await self.on_session_hook(session_id, cwd, tmux_session)

            return web.Response(text='ok')

        except Exception as e:
            logger.error(f"hook_error: {e}")
            return web.Response(text='error', status=500)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_hook_server.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/adapters/hook_server.py tests/test_hook_server.py
git commit -m "feat(adapters): implement HookServer for Claude session hooks"
```

---

## Task 4: Create services directory structure

**Files:**
- Create: `src/codogram/services/__init__.py`

**Step 1: Create services package**

```python
# src/codogram/services/__init__.py
"""Business logic services."""
```

**Step 2: Verify import works**

Run: `python -c "from codogram.services import *; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/services/__init__.py
git commit -m "feat: create services package"
```

---

## Task 5: Add read_last_assistant_entry to history_reader

**Files:**
- Modify: `src/codogram/history_reader.py`
- Test: `tests/test_history_reader.py`

**Step 1: Write failing test**

Add to `tests/test_history_reader.py`:

```python
def test_read_last_assistant_entry(tmp_path):
    """read_last_assistant_entry returns last assistant message."""
    from codogram.history_reader import read_last_assistant_entry

    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(
        '{"type": "user", "message": {"content": "hello"}}\n'
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi there!"}]}}\n'
        '{"type": "user", "message": {"content": "bye"}}\n'
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Goodbye!"}]}}\n'
    )

    entry = read_last_assistant_entry(jsonl)
    assert entry is not None
    assert entry["type"] == "assistant"
    assert entry["message"]["content"][0]["text"] == "Goodbye!"


def test_read_last_assistant_entry_with_tool_use(tmp_path):
    """read_last_assistant_entry returns assistant with tool_use."""
    from codogram.history_reader import read_last_assistant_entry

    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(
        '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"path": "/foo"}}]}}\n'
    )

    entry = read_last_assistant_entry(jsonl)
    assert entry is not None
    assert entry["message"]["content"][0]["type"] == "tool_use"
    assert entry["message"]["content"][0]["name"] == "Read"


def test_read_last_assistant_entry_empty_file(tmp_path):
    """read_last_assistant_entry returns None for empty file."""
    from codogram.history_reader import read_last_assistant_entry

    jsonl = tmp_path / "empty.jsonl"
    jsonl.write_text("")

    assert read_last_assistant_entry(jsonl) is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_history_reader.py::test_read_last_assistant_entry -v`
Expected: FAIL with "cannot import name 'read_last_assistant_entry'"

**Step 3: Implement read_last_assistant_entry**

Add to `src/codogram/history_reader.py`:

```python
def read_last_assistant_entry(jsonl_path: Path) -> dict | None:
    """Read the last assistant entry from session jsonl file.

    Returns the full entry dict or None if no assistant entry found.
    """
    if not jsonl_path.exists():
        return None

    try:
        last_assistant = None
        with open(jsonl_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "assistant":
                        last_assistant = entry
                except json.JSONDecodeError:
                    continue
        return last_assistant
    except Exception:
        return None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_history_reader.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/history_reader.py tests/test_history_reader.py
git commit -m "feat(history_reader): add read_last_assistant_entry function"
```

---

## Task 6: Implement SessionBinderService - bind_from_hook

**Files:**
- Create: `src/codogram/services/session_binder.py`
- Test: `tests/test_session_binder.py`

**Step 1: Write failing test**

Create `tests/test_session_binder.py`:

```python
# tests/test_session_binder.py
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_bind_from_hook_updates_thread():
    """bind_from_hook binds session to matching thread."""
    from codogram.services.session_binder import SessionBinderService
    from codogram.session_manager import ProjectState, ThreadInfo

    # Setup
    config = MagicMock()
    config.hooks_enabled = True
    config.hook_server_port = 8787

    tmux_adapter = MagicMock()
    history_adapter = MagicMock()

    binder = SessionBinderService(config, tmux_adapter, history_adapter)

    # Create project with thread
    project = ProjectState(project_name="test")
    project.cwd = "/test/path"
    project.chat_id = 123
    thread = ThreadInfo(thread_id=None, name="main")
    thread.session_id = "old-session"
    project.threads[None] = thread

    # Mock project_manager
    with patch('codogram.services.session_binder.project_manager') as mock_pm:
        mock_pm.projects = {"test": project}
        mock_pm._save = MagicMock()

        with patch('codogram.services.session_binder.compute_jsonl_path') as mock_path:
            mock_path.return_value = MagicMock()
            mock_path.return_value.__str__ = lambda x: "/path/to/new.jsonl"

            await binder.bind_from_hook(
                session_id="new-session-123",
                cwd="/test/path",
                tmux_session="claude-test"
            )

    # Thread should be updated
    assert thread.session_id == "new-session-123"


@pytest.mark.asyncio
async def test_bind_from_hook_ignores_same_session():
    """bind_from_hook does nothing if session unchanged."""
    from codogram.services.session_binder import SessionBinderService
    from codogram.session_manager import ProjectState, ThreadInfo

    config = MagicMock()
    config.hooks_enabled = True

    binder = SessionBinderService(config, MagicMock(), MagicMock())

    project = ProjectState(project_name="test")
    project.cwd = "/test/path"
    project.chat_id = 123
    thread = ThreadInfo(thread_id=None, name="main")
    thread.session_id = "same-session"
    project.threads[None] = thread

    with patch('codogram.services.session_binder.project_manager') as mock_pm:
        mock_pm.projects = {"test": project}
        mock_pm._save = MagicMock()

        await binder.bind_from_hook(
            session_id="same-session",
            cwd="/test/path",
            tmux_session="claude-test"
        )

    # Should not have called _save (no change)
    mock_pm._save.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_binder.py -v`
Expected: FAIL with "No module named 'codogram.services.session_binder'"

**Step 3: Implement SessionBinderService (hook part)**

Create `src/codogram/services/session_binder.py`:

```python
"""Session binding service with hooks and content matching fallback."""

from typing import TYPE_CHECKING

from ..logging_config import logger
from ..session_manager import ProjectState, ThreadInfo, project_manager
from ..history_reader import compute_jsonl_path

if TYPE_CHECKING:
    from ..adapters.hook_server import HookServer


class SessionBinderService:
    """Binds Claude sessions to threads.

    Primary: Hooks (exact tmux<->session mapping)
    Fallback: Content matching (for sessions without hooks)
    """

    def __init__(self, config, tmux_adapter, history_adapter):
        self.config = config
        self.tmux = tmux_adapter
        self.history = history_adapter
        self.hook_server: "HookServer | None" = None
        self._telegram_queue = None

    def set_telegram_queue(self, queue):
        """Set telegram queue for starting watchers."""
        self._telegram_queue = queue

    async def start_hook_server(self):
        """Start hook server if enabled."""
        if not self.config.hooks_enabled:
            logger.info("hooks_disabled: skipping hook server")
            return

        from ..adapters.hook_server import HookServer

        self.hook_server = HookServer(
            port=self.config.hook_server_port,
            on_session_hook=self.bind_from_hook
        )
        await self.hook_server.start()

    async def stop_hook_server(self):
        """Stop hook server."""
        if self.hook_server:
            await self.hook_server.stop()

    # === Primary: Hook-based binding ===

    async def bind_from_hook(self, session_id: str, cwd: str, tmux_session: str):
        """Bind session from hook data. Called by HookServer."""
        logger.debug(f"bind_from_hook: session={session_id[:8]}, tmux={tmux_session}, cwd={cwd}")

        # Find project by cwd
        project = self._find_project_by_cwd(cwd)
        if not project:
            logger.warning(f"hook_no_project: cwd={cwd}")
            return

        # Find thread by tmux session name
        thread = self._find_thread_by_tmux(project, tmux_session)
        if not thread:
            logger.warning(f"hook_no_thread: tmux={tmux_session}, project={project.project_name}")
            return

        # Check if session actually changed
        if thread.session_id == session_id:
            logger.debug(f"hook_same_session: {session_id[:8]}")
            return

        logger.info(f"hook_bind: project={project.project_name}, thread={thread.name}, "
                   f"old={thread.session_id[:8] if thread.session_id else None}, new={session_id[:8]}")

        await self._rebind_thread(project, thread, session_id)

    def _find_project_by_cwd(self, cwd: str) -> ProjectState | None:
        """Find project by working directory."""
        for project in project_manager.projects.values():
            if project.cwd == cwd:
                return project
        return None

    def _find_thread_by_tmux(self, project: ProjectState, tmux_session: str) -> ThreadInfo | None:
        """Find thread by tmux session name."""
        for thread in project.threads.values():
            expected_tmux = thread.get_tmux_session(project.project_name)
            if expected_tmux == tmux_session:
                return thread
        return None

    # === Rebind ===

    async def _rebind_thread(self, project: ProjectState, thread: ThreadInfo, new_session_id: str):
        """Rebind thread to new session."""
        # Cancel old watcher
        if thread.watcher_task:
            thread.watcher_task.cancel()
            thread.watcher_task = None

        # Update binding
        old_session = thread.session_id
        thread.session_id = new_session_id
        thread.jsonl_path = str(compute_jsonl_path(project.cwd, new_session_id))
        thread.awaiting_new_session = False

        logger.info(f"session_rebound: project={project.project_name}, thread={thread.name}, "
                   f"old={old_session[:8] if old_session else None}, new={new_session_id[:8]}")

        # Start new watcher if we have telegram_queue
        if self._telegram_queue:
            import asyncio
            from ..history_watcher import watch_thread_jsonl
            thread.watcher_task = asyncio.create_task(
                watch_thread_jsonl(None, project, thread, self._telegram_queue)
            )

        # Save config
        project_manager._save()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_binder.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/session_binder.py tests/test_session_binder.py
git commit -m "feat(services): implement SessionBinderService hook-based binding"
```

---

## Task 7: Implement SessionBinderService - content matching fallback

**Files:**
- Modify: `src/codogram/services/session_binder.py`
- Modify: `tests/test_session_binder.py`

**Step 1: Write failing test**

Add to `tests/test_session_binder.py`:

```python
@pytest.mark.asyncio
async def test_check_and_bind_single_thread():
    """check_and_bind uses find_session_for_project for single-thread."""
    from codogram.services.session_binder import SessionBinderService
    from codogram.session_manager import ProjectState, ThreadInfo

    config = MagicMock()
    config.hooks_enabled = False

    history_adapter = MagicMock()
    history_adapter.find_session_for_project = MagicMock(return_value="new-session")

    binder = SessionBinderService(config, MagicMock(), history_adapter)

    project = ProjectState(project_name="test")
    project.cwd = "/test/path"
    project.chat_id = 123
    # Single thread (thread_id=None, no topics)
    thread = ThreadInfo(thread_id=None, name="main")
    thread.session_id = "old-session"
    project.threads[None] = thread

    with patch('codogram.services.session_binder.project_manager') as mock_pm:
        mock_pm.projects = {"test": project}
        mock_pm._save = MagicMock()

        with patch('codogram.services.session_binder.compute_jsonl_path') as mock_path:
            mock_path.return_value = MagicMock()

            await binder.check_and_bind(project)

    assert thread.session_id == "new-session"


@pytest.mark.asyncio
async def test_check_and_bind_multi_thread_content_match(tmp_path):
    """check_and_bind uses content matching for multi-thread."""
    from codogram.services.session_binder import SessionBinderService
    from codogram.session_manager import ProjectState, ThreadInfo
    from pathlib import Path

    config = MagicMock()
    config.hooks_enabled = False

    # Setup history adapter
    history_adapter = MagicMock()
    history_adapter.read_last_assistant_entry = MagicMock(return_value={
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Hello world response"}]}
    })

    # Setup tmux adapter
    tmux_adapter = MagicMock()
    tmux_adapter.capture_pane = MagicMock(return_value="... Hello world response ...")

    binder = SessionBinderService(config, tmux_adapter, history_adapter)

    project = ProjectState(project_name="test")
    project.cwd = "/test/path"
    project.chat_id = 123

    # Multi-thread: has topics (thread_id is not None for at least one)
    thread1 = ThreadInfo(thread_id=None, name="main")
    thread1.session_id = "bound-session"
    project.threads[None] = thread1

    thread2 = ThreadInfo(thread_id=123, name="topic")
    thread2.session_id = None  # Unbound
    project.threads[123] = thread2

    with patch('codogram.services.session_binder.project_manager') as mock_pm:
        mock_pm.projects = {"test": project}
        mock_pm._save = MagicMock()

        # Mock _get_project_dir to return tmp_path with session file
        with patch.object(binder, '_get_project_dir', return_value=tmp_path):
            # Create fake unbound session
            (tmp_path / "unbound-session.jsonl").touch()

            with patch('codogram.services.session_binder.compute_jsonl_path', return_value=tmp_path / "unbound-session.jsonl"):
                await binder.check_and_bind(project)

    # thread2 should be bound via content match
    assert thread2.session_id == "unbound-session"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_binder.py::test_check_and_bind_single_thread -v`
Expected: FAIL with "SessionBinderService has no attribute 'check_and_bind'"

**Step 3: Add content matching methods**

Update `src/codogram/services/session_binder.py`:

```python
"""Session binding service with hooks and content matching fallback."""

from pathlib import Path
from typing import TYPE_CHECKING

from ..logging_config import logger
from ..session_manager import ProjectState, ThreadInfo, project_manager
from ..history_reader import compute_jsonl_path

if TYPE_CHECKING:
    from ..adapters.hook_server import HookServer


class SessionBinderService:
    """Binds Claude sessions to threads.

    Primary: Hooks (exact tmux<->session mapping)
    Fallback: Content matching (for sessions without hooks)
    """

    def __init__(self, config, tmux_adapter, history_adapter):
        self.config = config
        self.tmux = tmux_adapter
        self.history = history_adapter
        self.hook_server: "HookServer | None" = None
        self._telegram_queue = None

    def set_telegram_queue(self, queue):
        """Set telegram queue for starting watchers."""
        self._telegram_queue = queue

    async def start_hook_server(self):
        """Start hook server if enabled."""
        if not self.config.hooks_enabled:
            logger.info("hooks_disabled: skipping hook server")
            return

        from ..adapters.hook_server import HookServer

        self.hook_server = HookServer(
            port=self.config.hook_server_port,
            on_session_hook=self.bind_from_hook
        )
        await self.hook_server.start()

    async def stop_hook_server(self):
        """Stop hook server."""
        if self.hook_server:
            await self.hook_server.stop()

    # === Primary: Hook-based binding ===

    async def bind_from_hook(self, session_id: str, cwd: str, tmux_session: str):
        """Bind session from hook data. Called by HookServer."""
        logger.debug(f"bind_from_hook: session={session_id[:8]}, tmux={tmux_session}, cwd={cwd}")

        project = self._find_project_by_cwd(cwd)
        if not project:
            logger.warning(f"hook_no_project: cwd={cwd}")
            return

        thread = self._find_thread_by_tmux(project, tmux_session)
        if not thread:
            logger.warning(f"hook_no_thread: tmux={tmux_session}, project={project.project_name}")
            return

        if thread.session_id == session_id:
            logger.debug(f"hook_same_session: {session_id[:8]}")
            return

        logger.info(f"hook_bind: project={project.project_name}, thread={thread.name}, "
                   f"old={thread.session_id[:8] if thread.session_id else None}, new={session_id[:8]}")

        await self._rebind_thread(project, thread, session_id)

    def _find_project_by_cwd(self, cwd: str) -> ProjectState | None:
        """Find project by working directory."""
        for project in project_manager.projects.values():
            if project.cwd == cwd:
                return project
        return None

    def _find_thread_by_tmux(self, project: ProjectState, tmux_session: str) -> ThreadInfo | None:
        """Find thread by tmux session name."""
        for thread in project.threads.values():
            expected_tmux = thread.get_tmux_session(project.project_name)
            if expected_tmux == tmux_session:
                return thread
        return None

    # === Fallback: Content matching ===

    async def check_and_bind(self, project: ProjectState):
        """Check for unbound sessions and try to bind via content matching.

        Called by HistoryWatcher and on_message as fallback when hooks not available.
        """
        if self._is_multi_thread(project):
            await self._bind_multi_thread(project)
        else:
            await self._bind_single_thread(project)

    def _is_multi_thread(self, project: ProjectState) -> bool:
        """Project is multi-thread if has topics (thread_id != None)."""
        return any(t.thread_id is not None for t in project.threads.values())

    async def _bind_single_thread(self, project: ProjectState):
        """Legacy binding for single-thread projects."""
        thread = project.threads.get(None)
        if not thread:
            return

        new_session = self.history.find_session_for_project(project.cwd)

        if new_session and new_session != thread.session_id:
            logger.info(f"fallback_bind_single: {thread.session_id} -> {new_session}")
            await self._rebind_thread(project, thread, new_session)

    async def _bind_multi_thread(self, project: ProjectState):
        """Content matching for multi-thread projects."""
        unbound = self._find_unbound_sessions(project)

        for session_id in unbound:
            await self._try_bind_via_content(project, session_id)

    def _find_unbound_sessions(self, project: ProjectState) -> set[str]:
        """Find sessions not bound to any thread."""
        project_dir = self._get_project_dir(project.cwd)
        if not project_dir.exists():
            return set()

        all_sessions = {f.stem for f in project_dir.glob("*.jsonl")}
        bound = {t.session_id for t in project.threads.values() if t.session_id}
        return all_sessions - bound

    def _get_project_dir(self, cwd: str) -> Path:
        """Get project directory for jsonl files."""
        normalized = cwd.rstrip("/") or "/"
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        project_hash = normalized.replace("/", "-")
        return Path.home() / ".claude" / "projects" / project_hash

    async def _try_bind_via_content(self, project: ProjectState, session_id: str):
        """Try to match session content with tmux capture-pane."""
        jsonl_path = compute_jsonl_path(project.cwd, session_id)
        content = self._extract_matchable_content(jsonl_path)

        if not content:
            logger.debug(f"fallback_no_content: session={session_id[:8]}")
            return

        logger.debug(f"fallback_trying: session={session_id[:8]}, content={content[:50]}...")

        for thread in project.threads.values():
            if thread.session_id:
                continue  # Already bound

            tmux_name = thread.get_tmux_session(project.project_name)
            pane = self.tmux.capture_pane(tmux_name)

            if self._content_matches(content, pane):
                logger.info(f"fallback_bind_content: thread={thread.name}, session={session_id[:8]}")
                await self._rebind_thread(project, thread, session_id)
                break
        else:
            logger.debug(f"fallback_no_match: session={session_id[:8]}")

    def _extract_matchable_content(self, jsonl_path: Path) -> str | None:
        """Extract content for matching from last assistant entry."""
        last_entry = self.history.read_last_assistant_entry(jsonl_path)
        if not last_entry:
            return None

        content = last_entry.get("message", {}).get("content", [])

        for item in content:
            if item.get("type") == "text":
                return item.get("text", "")[:200]
            elif item.get("type") == "tool_use":
                name = item.get("name", "")
                inp = str(item.get("input", {}))[:100]
                return f"tool:{name}:{inp}"

        return None

    def _content_matches(self, content: str, pane: str) -> bool:
        """Check if content appears in tmux pane."""
        if not content or not pane:
            return False

        if content.startswith("tool:"):
            parts = content.split(":", 2)
            if len(parts) < 3:
                logger.warning(f"fallback_malformed_tool: {content}")
                return False
            _, tool_name, tool_input = parts
            return tool_name in pane and tool_input[:50] in pane
        else:
            return content[:150] in pane

    # === Rebind ===

    async def _rebind_thread(self, project: ProjectState, thread: ThreadInfo, new_session_id: str):
        """Rebind thread to new session."""
        if thread.watcher_task:
            thread.watcher_task.cancel()
            thread.watcher_task = None

        old_session = thread.session_id
        thread.session_id = new_session_id
        thread.jsonl_path = str(compute_jsonl_path(project.cwd, new_session_id))
        thread.awaiting_new_session = False

        logger.info(f"session_rebound: project={project.project_name}, thread={thread.name}, "
                   f"old={old_session[:8] if old_session else None}, new={new_session_id[:8]}")

        if self._telegram_queue:
            import asyncio
            from ..history_watcher import watch_thread_jsonl
            thread.watcher_task = asyncio.create_task(
                watch_thread_jsonl(None, project, thread, self._telegram_queue)
            )

        project_manager._save()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_binder.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/session_binder.py tests/test_session_binder.py
git commit -m "feat(services): add content matching fallback to SessionBinderService"
```

---

## Task 8: Create TmuxAdapter wrapper

**Files:**
- Create: `src/codogram/adapters/tmux_adapter.py`
- Test: `tests/test_tmux_adapter.py`

**Step 1: Write failing test**

Create `tests/test_tmux_adapter.py`:

```python
# tests/test_tmux_adapter.py
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import patch, MagicMock


def test_tmux_adapter_capture_pane():
    """TmuxAdapter.capture_pane calls tmux command."""
    from codogram.adapters.tmux_adapter import TmuxAdapter

    adapter = TmuxAdapter()

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="pane content\n")

        result = adapter.capture_pane("test-session")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "capture-pane" in args
        assert "-t" in args
        assert "test-session" in args
        assert "-S" in args  # Full scrollback
        assert "-" in args
        assert result == "pane content\n"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tmux_adapter.py -v`
Expected: FAIL with "No module named 'codogram.adapters.tmux_adapter'"

**Step 3: Implement TmuxAdapter**

Create `src/codogram/adapters/tmux_adapter.py`:

```python
"""Tmux adapter for session operations."""

import subprocess

from ..logging_config import logger


class TmuxAdapter:
    """Adapter for tmux operations needed by SessionBinder."""

    def capture_pane(self, session_name: str) -> str:
        """Capture entire scrollback from tmux pane.

        Uses -S - to get full history, not just visible area.
        """
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.debug(f"capture_pane_failed: {session_name}, rc={result.returncode}")
            return ""
        return result.stdout
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_tmux_adapter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/adapters/tmux_adapter.py tests/test_tmux_adapter.py
git commit -m "feat(adapters): add TmuxAdapter for capture_pane"
```

---

## Task 9: Create HistoryAdapter wrapper

**Files:**
- Create: `src/codogram/adapters/history_adapter.py`

**Step 1: Implement HistoryAdapter**

Create `src/codogram/adapters/history_adapter.py`:

```python
"""History adapter wrapping history_reader functions."""

from pathlib import Path

from ..history_reader import find_session_for_project, read_last_assistant_entry


class HistoryAdapter:
    """Adapter for history.jsonl operations needed by SessionBinder."""

    def find_session_for_project(self, cwd: str) -> str | None:
        """Find most recent session_id for a project."""
        return find_session_for_project(cwd)

    def read_last_assistant_entry(self, jsonl_path: Path) -> dict | None:
        """Read last assistant entry from session jsonl."""
        return read_last_assistant_entry(jsonl_path)
```

**Step 2: Verify import works**

Run: `python -c "from codogram.adapters.history_adapter import HistoryAdapter; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/adapters/history_adapter.py
git commit -m "feat(adapters): add HistoryAdapter wrapper"
```

---

## Task 10: Create hooks directory and session_hook.sh

**Files:**
- Create: `src/codogram/hooks/session_hook.sh`

**Step 1: Create hook script**

```bash
#!/bin/bash
# Claude Code SessionStart hook
# Sends session info to codogram hook server

set -e

# Read JSON input from Claude
input=$(cat)

# Parse fields
session_id=$(echo "$input" | jq -r '.session_id // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

if [ -z "$session_id" ]; then
    exit 0
fi

# Detect tmux session name
tmux_session=$(tmux display-message -p '#S' 2>/dev/null || echo "")

# Get port from environment or use default
HOOK_PORT="${CODOGRAM_HOOK_PORT:-8787}"

# Send to hook server
curl -s -X POST "http://127.0.0.1:${HOOK_PORT}/hook/session-start" \
    -H "Content-Type: application/json" \
    -d "{
        \"session_id\": \"$session_id\",
        \"cwd\": \"$cwd\",
        \"tmux_session\": \"$tmux_session\"
    }" >/dev/null 2>&1 || true

exit 0
```

**Step 2: Make executable and verify**

Run: `chmod +x src/codogram/hooks/session_hook.sh && ls -la src/codogram/hooks/`
Expected: Shows session_hook.sh with execute permissions

**Step 3: Commit**

```bash
git add src/codogram/hooks/session_hook.sh
git commit -m "feat(hooks): add session_hook.sh for Claude SessionStart"
```

---

## Task 11: Create setup_hooks.py CLI tool

**Files:**
- Create: `src/codogram/scripts/__init__.py`
- Create: `src/codogram/scripts/setup_hooks.py`

**Step 1: Create scripts package**

```python
# src/codogram/scripts/__init__.py
"""CLI scripts for codogram."""
```

**Step 2: Implement setup_hooks.py**

```python
#!/usr/bin/env python3
"""CLI tool to configure Claude hooks for codogram."""

import json
import shutil
from pathlib import Path


CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_SCRIPT = Path(__file__).parent.parent / "hooks" / "session_hook.sh"


def setup_hooks(port: int = 8787) -> bool:
    """Add SessionStart hook to Claude settings.

    Returns True if hooks were configured, False if user declined.
    """
    print("=== Codogram Hooks Setup ===\n")

    # Check if hook script exists
    if not HOOK_SCRIPT.exists():
        print(f"Error: Hook script not found at {HOOK_SCRIPT}")
        return False

    # Make hook script executable
    HOOK_SCRIPT.chmod(0o755)

    # Load existing settings
    settings = {}
    if CLAUDE_SETTINGS.exists():
        with open(CLAUDE_SETTINGS) as f:
            settings = json.load(f)

    # Check if hook already configured
    hooks = settings.get("hooks", {})
    session_start = hooks.get("SessionStart", [])

    hook_command = f'CODOGRAM_HOOK_PORT={port} {HOOK_SCRIPT}'

    already_configured = any(
        "session_hook.sh" in str(h.get("hooks", []))
        for h in session_start
    )

    if already_configured:
        print("Hooks already configured!")
        return True

    # Show what we're going to do
    print(f"This will add a SessionStart hook to {CLAUDE_SETTINGS}")
    print(f"Hook command: {hook_command}")
    print()

    # Ask for confirmation
    response = input("Proceed? [y/N]: ").strip().lower()
    if response != 'y':
        print("Aborted.")
        return False

    # Backup existing settings
    if CLAUDE_SETTINGS.exists():
        backup = CLAUDE_SETTINGS.with_suffix('.json.bak')
        shutil.copy(CLAUDE_SETTINGS, backup)
        print(f"Backed up existing settings to {backup}")

    # Add hook
    new_hook = {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": hook_command
            }
        ]
    }

    if "hooks" not in settings:
        settings["hooks"] = {}
    if "SessionStart" not in settings["hooks"]:
        settings["hooks"]["SessionStart"] = []

    settings["hooks"]["SessionStart"].append(new_hook)

    # Save
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAUDE_SETTINGS, 'w') as f:
        json.dump(settings, f, indent=2)

    print(f"\nHooks configured successfully!")
    print(f"Restart any running Claude sessions for hooks to take effect.")
    return True


def remove_hooks() -> bool:
    """Remove codogram hooks from Claude settings."""
    if not CLAUDE_SETTINGS.exists():
        print("No Claude settings found.")
        return True

    with open(CLAUDE_SETTINGS) as f:
        settings = json.load(f)

    hooks = settings.get("hooks", {})
    session_start = hooks.get("SessionStart", [])

    # Filter out codogram hooks
    filtered = [
        h for h in session_start
        if "session_hook.sh" not in str(h.get("hooks", []))
    ]

    if len(filtered) == len(session_start):
        print("No codogram hooks found.")
        return True

    settings["hooks"]["SessionStart"] = filtered

    with open(CLAUDE_SETTINGS, 'w') as f:
        json.dump(settings, f, indent=2)

    print("Codogram hooks removed.")
    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "remove":
        remove_hooks()
    else:
        setup_hooks()
```

**Step 3: Verify script runs**

Run: `python -c "from codogram.scripts.setup_hooks import setup_hooks; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add src/codogram/scripts/__init__.py src/codogram/scripts/setup_hooks.py
git commit -m "feat(scripts): add setup_hooks.py CLI tool"
```

---

## Task 12: Integrate SessionBinderService into main.py

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Update main.py**

```python
# src/codogram/main.py
import sys

# Fix module identity: ensure 'codogram.main' and '__main__' are the same object
if __name__ == '__main__':
    sys.modules['codogram.main'] = sys.modules['__main__']

import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router
from .session_manager import project_manager, ProjectState
from .tmux import TmuxSession
from .logging_config import setup_logging, logger
from .telegram_queue import TelegramQueue

telegram_queue: TelegramQueue | None = None
session_binder = None  # Global for access from other modules

async def main():
    global telegram_queue, session_binder

    setup_logging()
    logger.info("Starting Telegram Bridge (history.jsonl mode)")
    logger.info(f"Admin IDs: {settings.get_admin_ids()}")
    logger.info(f"Base dir: {settings.base_dir}")
    logger.info(f"Hooks enabled: {settings.hooks_enabled}")

    bot = Bot(token=settings.telegram_token)
    telegram_queue = TelegramQueue(bot)
    dp = Dispatcher()
    dp.include_router(router)

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Start Claude / show status"),
        BotCommand(command="session_new", description="Create new Claude thread"),
        BotCommand(command="session_close", description="Close Claude thread (use in topic)"),
        BotCommand(command="restart_session", description="Restart Claude session"),
        BotCommand(command="my_chat_id", description="Show your user ID"),
        BotCommand(command="esc", description="Send Escape to Claude"),
    ])

    # Create session binder service
    from .services.session_binder import SessionBinderService
    from .adapters.tmux_adapter import TmuxAdapter
    from .adapters.history_adapter import HistoryAdapter

    session_binder = SessionBinderService(
        config=settings,
        tmux_adapter=TmuxAdapter(),
        history_adapter=HistoryAdapter()
    )
    session_binder.set_telegram_queue(telegram_queue)

    # Start hook server if enabled
    await session_binder.start_hook_server()

    # Define task starters
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project, telegram_queue)

    async def start_watcher(project: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project, telegram_queue, send_missed)

    # Restore sessions from history.jsonl
    await project_manager.restore_projects(bot, start_poller, start_watcher, telegram_queue)

    # Start history watcher for session changes
    from .history_watcher import create_history_watcher
    history_watcher = await create_history_watcher(bot, start_poller, start_watcher, telegram_queue, session_binder)

    logger.info("History watcher started (15s polling)")

    # Start Telegram polling
    try:
        await dp.start_polling(bot)
    finally:
        if telegram_queue:
            await telegram_queue.shutdown()
        if session_binder:
            await session_binder.stop_hook_server()

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/main.py && echo "OK"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(main): integrate SessionBinderService with hook server"
```

---

## Task 13: Update HistoryWatcher to use SessionBinderService

**Files:**
- Modify: `src/codogram/history_watcher.py`

**Step 1: Update HistoryWatcher**

```python
"""Periodic watcher for history.jsonl changes."""
import asyncio
import time
from typing import TYPE_CHECKING

from aiogram import Bot

from .session_manager import project_manager, ProjectState, ThreadInfo

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue
    from .services.session_binder import SessionBinderService
from .history_reader import find_session_for_project
from .logging_config import logger
from .tmux import TmuxSession

REFRESH_INTERVAL = 15  # seconds


class HistoryWatcher:
    """Watches history.jsonl for session changes."""

    def __init__(self, bot: Bot, start_poller, start_watcher, telegram_queue: "TelegramQueue",
                 session_binder: "SessionBinderService | None" = None):
        self.bot = bot
        self.start_poller = start_poller
        self.start_watcher = start_watcher
        self.telegram_queue = telegram_queue
        self.session_binder = session_binder
        self.project_manager = project_manager
        self._last_mtime = 0
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the watcher task."""
        self._task = asyncio.create_task(self._watch_loop())
        return self._task

    async def stop(self):
        """Stop the watcher task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch_loop(self):
        """Main watch loop."""
        while True:
            try:
                await self._check_for_changes()
            except Exception as e:
                logger.error("watch_loop_error", extra={"error": str(e)})

            await asyncio.sleep(REFRESH_INTERVAL)

    async def _check_for_changes(self):
        """Check tmux health and session changes for all projects."""
        from .session_manager import should_cleanup_project

        for project in list(self.project_manager.projects.values()):
            if not project.chat_id or not project.cwd:
                continue

            # 1. Check if should cleanup (inactive > 30 days)
            if should_cleanup_project(project):
                logger.info("project_cleanup", extra={"project": project.project_name, "reason": "inactive_30_days"})
                # Cancel all thread tasks
                for thread in project.threads.values():
                    if thread.watcher_task:
                        thread.watcher_task.cancel()
                    if thread.poller_task:
                        thread.poller_task.cancel()
                # Cancel legacy tasks
                if project.watcher_task:
                    project.watcher_task.cancel()
                if project.poller_task:
                    project.poller_task.cancel()
                del self.project_manager.projects[project.project_name]
                continue

            # 2. Check thread health (tmux died detection for ALL threads)
            for thread in list(project.threads.values()):
                # Skip if awaiting or binding
                if thread.awaiting_new_session:
                    continue
                if thread.binding_task and not thread.binding_task.done():
                    continue

                tmux_name = thread.get_tmux_session(project.project_name)
                tmux = TmuxSession(tmux_name, project.cwd)

                # Check if tmux died
                if thread.session_id and not tmux.exists():
                    logger.warning(f"thread_tmux_died: project={project.project_name}, thread={thread.name}")

                    # Stop thread tasks
                    if thread.watcher_task:
                        thread.watcher_task.cancel()
                        thread.watcher_task = None
                    if thread.poller_task:
                        thread.poller_task.cancel()
                        thread.poller_task = None

                    # Notify user through queue
                    from .telegram_queue import OutgoingBatch
                    try:
                        batch = OutgoingBatch(
                            chat_id=project.chat_id,
                            thread_id=thread.thread_id,
                            messages=[{"text": f"⚠️ Claude session closed: {thread.name}"}],
                        )
                        await self.telegram_queue.enqueue_nowait(batch)
                    except Exception:
                        pass

                    # Reset thread state
                    thread.session_id = None
                    thread.jsonl_path = None

            # 3. Fallback session binding (for sessions without hooks)
            if self.session_binder:
                await self.session_binder.check_and_bind(project)


BINDING_TIMEOUT = 300  # 5 minutes
BINDING_INTERVAL = 0.5  # seconds


async def watch_thread_jsonl(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue"):
    """Watch jsonl for a specific thread and send messages through queue."""
    from .watcher import JsonlWatcher, _entry_to_messages
    from .telegram_queue import OutgoingBatch
    from pathlib import Path

    if not thread.jsonl_path:
        return

    watcher = JsonlWatcher(Path(thread.jsonl_path))

    try:
        async for entry in watcher.watch():
            try:
                messages = _entry_to_messages(entry)
                if messages:
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    await telegram_queue.enqueue_nowait(batch)
            except Exception as e:
                logger.error(f"watch_thread_error: {e}")
    except asyncio.CancelledError:
        logger.info(f"watch_thread_cancelled: thread={thread.name}")
        raise


async def poll_for_session_thread(
    project: ProjectState,
    thread: ThreadInfo,
    bot: Bot,
    start_poller,
    start_watcher,
    telegram_queue: "TelegramQueue",
) -> None:
    """Poll for a session that matches thread.last_sent_message.

    Scans ALL sessions for this cwd (not just the latest) because multiple
    threads may have different Claude sessions in the same project directory.
    """
    try:
        from .history_reader import find_session_by_user_message
    except Exception as e:
        logger.error(f"poll_for_session_thread: import error: {e}")
        return

    logger.debug(f"poll_for_session_thread called: cwd={project.cwd}, msg={thread.last_sent_message}")

    if not project.cwd or not thread.last_sent_message:
        logger.warning("poll_for_session_thread: missing cwd or last_sent_message")
        return

    logger.debug("poll_for_session_thread: passed validation, starting loop")
    start_time = time.time()

    try:
        logger.debug(f"poll_for_session_thread_start: project={project.project_name}, thread={thread.name}")
    except Exception as e:
        logger.error(f"poll_for_session_thread: logging error: {e}")

    logger.debug("poll_for_session_thread: entering while loop")
    while time.time() - start_time < BINDING_TIMEOUT:
        try:
            # Scan ALL sessions for this cwd to find one with matching user message
            result = find_session_by_user_message(project.cwd, thread.last_sent_message)
            logger.debug(f"poll_for_session_thread: search result={result is not None}")

            if result:
                session_id, jsonl_path = result

                logger.info(f"session_bound_thread: project={project.project_name}, thread={thread.name}, session={session_id[:8]}")

                thread.session_id = session_id
                thread.jsonl_path = str(jsonl_path)
                thread.awaiting_new_session = False

                # Start thread-specific watcher
                if not thread.watcher_task or thread.watcher_task.done():
                    thread.watcher_task = asyncio.create_task(
                        watch_thread_jsonl(bot, project, thread, telegram_queue)
                    )

                # Start thread-specific permission poller
                from .permission_poller import create_poller_task_for_thread
                if not thread.poller_task or thread.poller_task.done():
                    thread.poller_task = await create_poller_task_for_thread(bot, project, thread, telegram_queue)

                logger.info(f"thread_watcher_started: thread={thread.name}, session={session_id[:8]}")
                return

        except Exception as e:
            logger.warning(f"poll_for_session_thread_error: {e}")

        await asyncio.sleep(BINDING_INTERVAL)

    # Timeout
    logger.warning(f"poll_for_session_thread_timeout: project={project.project_name}, thread={thread.name}")
    thread.awaiting_new_session = False
    try:
        from .telegram_queue import OutgoingBatch
        batch = OutgoingBatch(
            chat_id=project.chat_id,
            thread_id=thread.thread_id,
            messages=[{"text": "⚠️ Сессия не обнаружена. Проверьте что Claude запущен."}],
        )
        await telegram_queue.enqueue_nowait(batch)
    except Exception:
        pass


async def create_history_watcher(bot: Bot, start_poller, start_watcher, telegram_queue: "TelegramQueue",
                                  session_binder: "SessionBinderService | None" = None) -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher, telegram_queue, session_binder)
    await watcher.start()
    return watcher
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/history_watcher.py && echo "OK"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "feat(history_watcher): integrate SessionBinderService for fallback binding"
```

---

## Task 14: Remove check_session_for_thread from bot.py

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Update bot.py to remove check_session_for_thread call**

Find the section around line 1386-1389 and replace:

```python
    else:
        # Session already bound - check if it changed (user might have done /new in tmux)
        from .history_watcher import check_session_for_thread
        await check_session_for_thread(project, thread, message.bot, start_poller, start_watcher)
```

With:

```python
    else:
        # Session already bound - session changes are now handled by:
        # 1. HookServer (primary) - receives Claude SessionStart hooks
        # 2. SessionBinderService.check_and_bind() (fallback) - content matching
        # Called by HistoryWatcher every 15s
        pass
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/bot.py && echo "OK"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove check_session_for_thread (replaced by SessionBinderService)"
```

---

## Task 15: Update tests for HistoryWatcher

**Files:**
- Modify: `tests/test_history_watcher.py`

**Step 1: Update test to reflect new API**

```python
# tests/test_history_watcher.py
import os
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_history_watcher_calls_session_binder():
    """Test that HistoryWatcher calls session_binder.check_and_bind."""
    from codogram.history_watcher import HistoryWatcher
    from codogram.session_manager import ThreadInfo

    bot = MagicMock()
    start_poller = AsyncMock()
    start_watcher = AsyncMock()
    telegram_queue = MagicMock()
    telegram_queue.enqueue_nowait = AsyncMock()

    session_binder = MagicMock()
    session_binder.check_and_bind = AsyncMock()

    watcher = HistoryWatcher(bot, start_poller, start_watcher, telegram_queue, session_binder)

    # Mock thread
    mock_thread = MagicMock(spec=ThreadInfo)
    mock_thread.thread_id = None
    mock_thread.name = "main"
    mock_thread.session_id = "session-123"
    mock_thread.watcher_task = None
    mock_thread.poller_task = None
    mock_thread.awaiting_new_session = False
    mock_thread.binding_task = None
    mock_thread.get_tmux_session.return_value = "claude-test"

    # Mock project
    mock_project = MagicMock()
    mock_project.chat_id = 123
    mock_project.cwd = "/test/path"
    mock_project.project_name = "test"
    mock_project.threads = {None: mock_thread}
    mock_project.watcher_task = None
    mock_project.poller_task = None

    mock_pm = MagicMock()
    mock_pm.projects = {"test": mock_project}
    watcher.project_manager = mock_pm

    with patch('codogram.session_manager.should_cleanup_project', return_value=False):
        with patch('codogram.history_watcher.TmuxSession') as mock_tmux:
            mock_tmux.return_value.exists.return_value = True

            await watcher._check_for_changes()

            # Should have called session_binder.check_and_bind
            session_binder.check_and_bind.assert_called_once_with(mock_project)


@pytest.mark.asyncio
async def test_history_watcher_detects_tmux_death():
    """Test that HistoryWatcher detects when tmux session dies."""
    from codogram.history_watcher import HistoryWatcher
    from codogram.session_manager import ThreadInfo

    bot = MagicMock()
    telegram_queue = MagicMock()
    telegram_queue.enqueue_nowait = AsyncMock()

    watcher = HistoryWatcher(bot, AsyncMock(), AsyncMock(), telegram_queue, None)

    mock_thread = MagicMock(spec=ThreadInfo)
    mock_thread.thread_id = None
    mock_thread.name = "main"
    mock_thread.session_id = "session-123"  # Has session
    mock_thread.watcher_task = MagicMock()
    mock_thread.poller_task = MagicMock()
    mock_thread.awaiting_new_session = False
    mock_thread.binding_task = None
    mock_thread.get_tmux_session.return_value = "claude-test"

    mock_project = MagicMock()
    mock_project.chat_id = 123
    mock_project.cwd = "/test/path"
    mock_project.project_name = "test"
    mock_project.threads = {None: mock_thread}
    mock_project.watcher_task = None
    mock_project.poller_task = None

    mock_pm = MagicMock()
    mock_pm.projects = {"test": mock_project}
    watcher.project_manager = mock_pm

    with patch('codogram.session_manager.should_cleanup_project', return_value=False):
        with patch('codogram.history_watcher.TmuxSession') as mock_tmux:
            mock_tmux.return_value.exists.return_value = False  # Tmux died

            await watcher._check_for_changes()

            # Thread tasks should be cancelled
            mock_thread.watcher_task.cancel.assert_called_once()
            mock_thread.poller_task.cancel.assert_called_once()

            # Session should be reset
            assert mock_thread.session_id is None
            assert mock_thread.jsonl_path is None
```

**Step 2: Run tests**

Run: `pytest tests/test_history_watcher.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_history_watcher.py
git commit -m "test(history_watcher): update tests for SessionBinderService integration"
```

---

## Task 16: Run full test suite and verify

**Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 2: Verify bot can start (dry run)**

Run: `python -c "from codogram.main import main; print('Import OK')"`
Expected: Import OK

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete session binder implementation

- Add HookServer for Claude SessionStart hooks
- Add SessionBinderService with hook binding + content matching fallback
- Add setup_hooks.py CLI for user configuration
- Integrate into main.py and HistoryWatcher
- Remove deprecated check_session_for_thread

Fixes: thread session mixup bug"
```

---

## Task 17: Update documentation

**Files:**
- Modify: `docs/setup.md` or create `docs/hooks-setup.md`

**Step 1: Create hooks documentation**

Create `docs/hooks-setup.md`:

```markdown
# Настройка Hooks для Codogram

## Зачем нужны Hooks?

Hooks позволяют Claude напрямую сообщать Codogram о смене сессии (при /compact, /new и т.д.).
Это решает проблему с "перепутыванием" сессий в разных тредах.

## Установка

```bash
cd agent-tools/codogram
python -m codogram.scripts.setup_hooks
```

Скрипт:
1. Создаст бэкап `~/.claude/settings.json`
2. Добавит SessionStart hook для Codogram
3. Попросит подтверждения перед внесением изменений

## Проверка

После установки в `~/.claude/settings.json` появится:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "CODOGRAM_HOOK_PORT=8787 /path/to/session_hook.sh"
          }
        ]
      }
    ]
  }
}
```

## Удаление

```bash
python -m codogram.scripts.setup_hooks remove
```

## Troubleshooting

### Hooks не срабатывают

1. Проверьте что бот запущен (`./restart.sh`)
2. Проверьте логи: `journalctl -u codogram -f`
3. Проверьте что порт 8787 свободен: `lsof -i :8787`

### Fallback режим

Если hooks не настроены, Codogram использует content matching (менее надёжный).
Для отключения hooks: `HOOKS_ENABLED=false` в `.env`
```

**Step 2: Commit documentation**

```bash
git add docs/hooks-setup.md
git commit -m "docs: add hooks setup guide"
```

---

## Summary

**Total tasks:** 17
**Estimated time:** ~2-3 hours

**Key changes:**
1. `config.py` - hooks_enabled, hook_server_port settings
2. `adapters/hook_server.py` - HTTP server for Claude hooks
3. `adapters/tmux_adapter.py` - TmuxAdapter for capture_pane
4. `adapters/history_adapter.py` - HistoryAdapter wrapper
5. `services/session_binder.py` - Main service with hook + fallback binding
6. `hooks/session_hook.sh` - Shell script for Claude hook
7. `scripts/setup_hooks.py` - CLI for user setup
8. `main.py` - Integration point
9. `history_watcher.py` - Uses SessionBinderService
10. `bot.py` - Removed check_session_for_thread call
11. `history_reader.py` - Added read_last_assistant_entry

**Testing:**
- Unit tests for each component
- Integration via HistoryWatcher
- Manual testing with/without hooks
