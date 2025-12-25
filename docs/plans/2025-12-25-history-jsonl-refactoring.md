# history.jsonl Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hook-based session discovery with history.jsonl polling for zero-config experience.

**Architecture:** Read session_id from ~/.claude/history.jsonl by project cwd. Periodic refresh (10s) detects session changes. Remove HTTP endpoints and hooks.

**Tech Stack:** Python asyncio, aiofiles (optional), pathlib

---

## Task 1: Add HistoryReader utility

**Files:**
- Create: `src/telegram_bridge/history_reader.py`
- Test: `tests/test_history_reader.py`

**Step 1: Write the failing test**

```python
# tests/test_history_reader.py
import json
import tempfile
from pathlib import Path
from telegram_bridge.history_reader import find_session_for_project

def test_find_session_for_project():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({"project": "/home/user/project-a", "sessionId": "aaa-111"}) + "\n")
        f.write(json.dumps({"project": "/home/user/project-b", "sessionId": "bbb-222"}) + "\n")
        f.write(json.dumps({"project": "/home/user/project-a", "sessionId": "aaa-333"}) + "\n")
        history_path = Path(f.name)

    # Should return last session for project-a
    result = find_session_for_project("/home/user/project-a", history_path)
    assert result == "aaa-333"

    # Should return session for project-b
    result = find_session_for_project("/home/user/project-b", history_path)
    assert result == "bbb-222"

    # Should return None for unknown project
    result = find_session_for_project("/home/user/unknown", history_path)
    assert result is None

    history_path.unlink()

def test_find_session_empty_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)

    result = find_session_for_project("/any/path", history_path)
    assert result is None

    history_path.unlink()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_history_reader.py -v`
Expected: FAIL with "No module named 'telegram_bridge.history_reader'"

**Step 3: Write minimal implementation**

```python
# src/telegram_bridge/history_reader.py
"""Read session info from Claude's history.jsonl."""
import json
from pathlib import Path

HISTORY_PATH = Path.home() / ".claude" / "history.jsonl"

def find_session_for_project(cwd: str, history_path: Path = HISTORY_PATH) -> str | None:
    """Find the most recent session_id for a project by cwd.

    Reads history.jsonl from end to find last entry matching project.
    """
    if not history_path.exists():
        return None

    try:
        lines = history_path.read_text().splitlines()
    except Exception:
        return None

    # Read from end to find most recent
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("project") == cwd:
                return entry.get("sessionId")
        except json.JSONDecodeError:
            continue

    return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_history_reader.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/history_reader.py tests/test_history_reader.py
git commit -m "feat(telegram-bridge): add history_reader for session discovery"
```

---

## Task 2: Add tmux discovery by cwd

**Files:**
- Modify: `src/telegram_bridge/tmux.py`
- Test: `tests/test_tmux.py` (add test)

**Step 1: Write the failing test**

```python
# tests/test_tmux.py (append to existing or create)
from telegram_bridge.tmux import find_tmux_by_cwd

def test_find_tmux_by_cwd_not_found(mocker):
    # Mock subprocess to return no matching sessions
    mocker.patch('subprocess.run', return_value=mocker.Mock(
        returncode=0,
        stdout=""
    ))

    result = find_tmux_by_cwd("/home/user/project")
    assert result is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tmux.py::test_find_tmux_by_cwd_not_found -v`
Expected: FAIL with "cannot import name 'find_tmux_by_cwd'"

**Step 3: Write minimal implementation**

```python
# Add to src/telegram_bridge/tmux.py

def find_tmux_by_cwd(cwd: str) -> str | None:
    """Find tmux session by pane current path.

    Returns session name if found, None otherwise.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{session_name} #{pane_current_path}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                session_name, pane_path = parts
                if pane_path == cwd:
                    return session_name

        return None
    except Exception:
        return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_tmux.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/tmux.py tests/test_tmux.py
git commit -m "feat(telegram-bridge): add find_tmux_by_cwd function"
```

---

## Task 3: Add compute_jsonl_path utility

**Files:**
- Modify: `src/telegram_bridge/history_reader.py`
- Test: `tests/test_history_reader.py` (add test)

**Step 1: Write the failing test**

```python
# Add to tests/test_history_reader.py
from telegram_bridge.history_reader import compute_jsonl_path

def test_compute_jsonl_path():
    result = compute_jsonl_path("/home/user/dev/my-project", "abc-123-def")
    expected = Path.home() / ".claude" / "projects" / "-home-user-dev-my-project" / "abc-123-def.jsonl"
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_history_reader.py::test_compute_jsonl_path -v`
Expected: FAIL with "cannot import name 'compute_jsonl_path'"

**Step 3: Write minimal implementation**

```python
# Add to src/telegram_bridge/history_reader.py

def compute_jsonl_path(cwd: str, session_id: str) -> Path:
    """Compute jsonl path from cwd and session_id."""
    project_hash = cwd.replace("/", "-")
    return Path.home() / ".claude" / "projects" / project_hash / f"{session_id}.jsonl"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_history_reader.py::test_compute_jsonl_path -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/history_reader.py tests/test_history_reader.py
git commit -m "feat(telegram-bridge): add compute_jsonl_path utility"
```

---

## Task 4: Add refresh_project_session method

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_session_manager.py or create new
import pytest
from telegram_bridge.session_manager import ProjectManager, ProjectState

def test_refresh_project_session(mocker, tmp_path):
    # Mock history_reader
    mocker.patch(
        'telegram_bridge.session_manager.find_session_for_project',
        return_value="new-session-123"
    )
    mocker.patch(
        'telegram_bridge.session_manager.compute_jsonl_path',
        return_value=tmp_path / "test.jsonl"
    )

    # Create test jsonl file
    (tmp_path / "test.jsonl").touch()

    manager = ProjectManager()
    project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
    manager.projects["test"] = project

    changed = manager.refresh_project_session(project)

    assert changed is True
    assert project.claude_session_id == "new-session-123"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_refresh_project_session -v`
Expected: FAIL with "ProjectManager has no attribute 'refresh_project_session'"

**Step 3: Write minimal implementation**

```python
# Add import at top of session_manager.py
from .history_reader import find_session_for_project, compute_jsonl_path

# Add method to ProjectManager class
def refresh_project_session(self, project: ProjectState) -> bool:
    """Refresh session_id from history.jsonl.

    Returns True if session changed, False otherwise.
    """
    if not project.cwd:
        return False

    new_session_id = find_session_for_project(project.cwd)
    if not new_session_id:
        return False

    if new_session_id == project.claude_session_id:
        return False  # No change

    # Session changed
    project.claude_session_id = new_session_id

    # Compute jsonl path
    jsonl_path = compute_jsonl_path(project.cwd, new_session_id)
    if jsonl_path.exists():
        project.jsonl_path = str(jsonl_path)
    else:
        project.jsonl_path = None

    return True
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py::test_refresh_project_session -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/session_manager.py tests/test_session_manager.py
git commit -m "feat(telegram-bridge): add refresh_project_session method"
```

---

## Task 5: Add HistoryWatcher periodic task

**Files:**
- Create: `src/telegram_bridge/history_watcher.py`

**Step 1: Write implementation**

```python
# src/telegram_bridge/history_watcher.py
"""Periodic watcher for history.jsonl changes."""
import asyncio
from pathlib import Path
from aiogram import Bot

from .session_manager import project_manager, ProjectState
from .history_reader import HISTORY_PATH

REFRESH_INTERVAL = 10  # seconds

class HistoryWatcher:
    """Watches history.jsonl for session changes."""

    def __init__(self, bot: Bot, start_poller, start_watcher):
        self.bot = bot
        self.start_poller = start_poller
        self.start_watcher = start_watcher
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
                print(f"HistoryWatcher error: {e}")

            await asyncio.sleep(REFRESH_INTERVAL)

    async def _check_for_changes(self):
        """Check if history.jsonl changed and refresh sessions."""
        if not HISTORY_PATH.exists():
            return

        # Quick mtime check
        mtime = HISTORY_PATH.stat().st_mtime
        if mtime == self._last_mtime:
            return
        self._last_mtime = mtime

        # Check each project with chat_id
        for project in project_manager.projects.values():
            if not project.chat_id or not project.cwd:
                continue

            old_session = project.claude_session_id
            changed = project_manager.refresh_project_session(project)

            if changed:
                print(f"HistoryWatcher: session changed for {project.project_name}: {old_session} -> {project.claude_session_id}")

                # Restart watcher if needed
                if project.watcher_task:
                    project.watcher_task.cancel()
                    project.watcher_task = None

                await project_manager._maybe_start_tasks(
                    project, self.start_poller, self.start_watcher
                )


async def create_history_watcher(bot: Bot, start_poller, start_watcher) -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher)
    await watcher.start()
    return watcher
```

**Step 2: Run syntax check**

Run: `python -m py_compile src/telegram_bridge/history_watcher.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/telegram_bridge/history_watcher.py
git commit -m "feat(telegram-bridge): add HistoryWatcher periodic task"
```

---

## Task 6: Simplify restore_projects to use history.jsonl

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Rewrite restore_projects**

Replace the existing `restore_projects` method:

```python
async def restore_projects(self, start_poller, start_watcher) -> None:
    """Restore sessions from history.jsonl after bot restart."""
    from .tmux import find_tmux_by_cwd

    for project in self.projects.values():
        if not project.chat_id or not project.cwd:
            continue

        # 1. Find session_id from history.jsonl
        self.refresh_project_session(project)

        # 2. Find tmux by cwd or convention
        if not project.tmux_session:
            tmux = find_tmux_by_cwd(project.cwd)
            if tmux:
                project.tmux_session = tmux
            else:
                # Fallback to convention
                for pattern in [f"claude-{project.project_name}", project.project_name]:
                    from .tmux import TmuxSession
                    t = TmuxSession(pattern, project.cwd)
                    if t.exists():
                        project.tmux_session = pattern
                        break

        # 3. Start tasks if ready
        await self._maybe_start_tasks(project, start_poller, start_watcher)

    self._save()
```

**Step 2: Run existing tests**

Run: `pytest tests/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/telegram_bridge/session_manager.py
git commit -m "refactor(telegram-bridge): simplify restore_projects to use history.jsonl"
```

---

## Task 7: Remove hook-related code from session_manager.py

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Remove methods**

Delete these methods from `ProjectManager`:
- `update_from_hook` (lines 129-152)
- `handle_session_end` (lines 192-210)
- `get_by_session` (lines 85-90)

**Step 2: Remove sessions from _save**

Update `_save` method to remove sessions section:

```python
def _save(self) -> None:
    """Persist to disk."""
    self._config["projects"] = {
        name: {"chat_id": p.chat_id, "cwd": p.cwd}
        for name, p in self.projects.items()
        if p.chat_id is not None
    }
    # Remove sessions - no longer needed
    self._config.pop("sessions", None)
    save_config(self._config)
```

**Step 3: Run syntax check**

Run: `python -m py_compile src/telegram_bridge/session_manager.py`
Expected: No output (success)

**Step 4: Commit**

```bash
git add src/telegram_bridge/session_manager.py
git commit -m "refactor(telegram-bridge): remove hook-related methods from session_manager"
```

---

## Task 8: Remove hook HTTP endpoints from main.py

**Files:**
- Modify: `src/telegram_bridge/main.py`

**Step 1: Remove handlers**

Delete:
- `handle_register` function (lines 13-45)
- `handle_unregister` function (lines 47-56)

**Step 2: Update run_http_server**

```python
async def run_http_server(bot: Bot) -> None:
    """Run HTTP server for debug endpoint."""
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/debug", handle_debug)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", settings.http_port)
    await site.start()
    print(f"HTTP server running on http://localhost:{settings.http_port}")
```

**Step 3: Add HistoryWatcher to main**

Update `main()` function:

```python
async def main():
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Starting bridge")
    print(f"Admin IDs: {settings.get_admin_ids()}")
    print(f"Base dir: {settings.base_dir}")

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Start Claude / show status"),
        BotCommand(command="restart_session", description="Restart Claude session"),
        BotCommand(command="my_chat_id", description="Show your user ID"),
        BotCommand(command="esc", description="Send Escape to Claude"),
    ])

    # Start HTTP server (debug only)
    await run_http_server(bot)

    # Define task starters
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project)

    async def start_watcher(project: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project)

    # Restore sessions from history.jsonl
    await project_manager.restore_projects(start_poller, start_watcher)

    # Start history watcher for session changes
    from .history_watcher import create_history_watcher
    await create_history_watcher(bot, start_poller, start_watcher)

    # Start Telegram polling
    await dp.start_polling(bot)
```

**Step 4: Run syntax check**

Run: `python -m py_compile src/telegram_bridge/main.py`
Expected: No output (success)

**Step 5: Commit**

```bash
git add src/telegram_bridge/main.py
git commit -m "refactor(telegram-bridge): remove hook endpoints, add HistoryWatcher"
```

---

## Task 9: Update config.py default

**Files:**
- Modify: `src/telegram_bridge/config.py`

**Step 1: Remove sessions from default config**

```python
def default_config() -> dict:
    return {"projects": {}}
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/config.py
git commit -m "refactor(telegram-bridge): remove sessions from default config"
```

---

## Task 10: Mark hooks as deprecated

**Files:**
- Modify: `hooks/session-start.sh`
- Modify: `hooks/session-end.sh`

**Step 1: Add deprecation notice**

Add to top of both files:

```bash
#!/bin/bash
# DEPRECATED: This hook is no longer needed.
# telegram-bridge now uses history.jsonl for session discovery.
# You can remove this hook from ~/.claude/settings.json
#
# Keeping for backwards compatibility - does nothing.
exit 0
```

**Step 2: Commit**

```bash
git add hooks/
git commit -m "deprecate(telegram-bridge): mark hooks as deprecated"
```

---

## Task 11: Integration test

**Files:**
- None (manual testing)

**Step 1: Restart bot**

```bash
/home/superbereza/dev/personal-agent/agent-tools/telegram-bridge/restart.sh
```

**Step 2: Check debug endpoint**

```bash
curl http://localhost:8765/debug | jq
```

Expected: Projects with session_id populated from history.jsonl

**Step 3: Test /start in Telegram**

Send `/start` in project chat.
Expected: Connects to existing Claude session without hooks.

**Step 4: Verify watcher works**

Send a message in Claude, verify it appears in Telegram.

**Step 5: Test session change**

Run `/resume` in Claude, wait 10 seconds.
Expected: Watcher reconnects to new session automatically.

---

## Task 12: Update documentation

**Files:**
- Modify: `docs/setup.md`
- Modify: `CLAUDE.md`

**Step 1: Remove hook setup instructions**

Remove or update any instructions about configuring hooks in `~/.claude/settings.json`.

**Step 2: Document new architecture**

Add note about automatic session discovery via history.jsonl.

**Step 3: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "docs(telegram-bridge): update for history.jsonl architecture"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | HistoryReader utility | history_reader.py |
| 2 | tmux discovery by cwd | tmux.py |
| 3 | compute_jsonl_path | history_reader.py |
| 4 | refresh_project_session | session_manager.py |
| 5 | HistoryWatcher task | history_watcher.py |
| 6 | Simplify restore_projects | session_manager.py |
| 7 | Remove hook methods | session_manager.py |
| 8 | Remove hook endpoints | main.py |
| 9 | Update config default | config.py |
| 10 | Deprecate hooks | hooks/*.sh |
| 11 | Integration test | - |
| 12 | Update docs | docs/, CLAUDE.md |
