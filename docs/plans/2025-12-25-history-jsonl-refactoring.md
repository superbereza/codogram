# history.jsonl Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hook-based session discovery with history.jsonl polling for zero-config experience.

**Architecture:** Read session_id from ~/.claude/history.jsonl by project cwd. Periodic refresh (15s) detects session changes. Remove HTTP server and hooks completely.

**Tech Stack:** Python asyncio, pathlib

**Key changes from design:**
- Model data simplified: Optional fields instead of dict (session_id, tmux_session)
- Terminology: tmux_session (long-lived) vs session_id (changes on /new, /resume)
- jsonl_path computed via formula: `~/.claude/projects/{cwd.replace("/", "-")}/{session_id}.jsonl`
- Truncated file detection in polling (size < last_size → reset cache)
- Cleanup by jsonl mtime (not last_activity)
- Constraints: one Claude per tmux, cd not tracked
- /start logic: two independent discoveries (tmux + session)

---

## Task 1: Add HistoryReader utility with truncation detection

**Files:**
- Create: `src/telegram_bridge/history_reader.py`
- Test: `tests/test_history_reader.py`

**Step 1: Write the failing test**

```python
# tests/test_history_reader.py
import json
import tempfile
from pathlib import Path
from telegram_bridge.history_reader import find_session_for_project, reset_history_cache

def test_find_session_for_project():
    reset_history_cache()  # Clean state

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
    reset_history_cache()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)

    result = find_session_for_project("/any/path", history_path)
    assert result is None

    history_path.unlink()

def test_incremental_reading():
    """Test that incremental reading works correctly."""
    reset_history_cache()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)
        f.write(json.dumps({"project": "/test", "sessionId": "first"}) + "\n")
        f.flush()

        # First read
        result = find_session_for_project("/test", history_path)
        assert result == "first"

        # Append new entry
        f.write(json.dumps({"project": "/test", "sessionId": "second"}) + "\n")
        f.flush()

        # Should pick up new entry
        result = find_session_for_project("/test", history_path)
        assert result == "second"

    history_path.unlink()

def test_truncated_file_detection():
    """Test that file truncation is detected and cache is reset."""
    reset_history_cache()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)
        # Write initial data
        f.write(json.dumps({"project": "/test", "sessionId": "first"}) + "\n")
        f.write(json.dumps({"project": "/test", "sessionId": "second"}) + "\n")
        f.flush()

        # First read
        result = find_session_for_project("/test", history_path)
        assert result == "second"

    # Simulate truncation - rewrite file with less data
    with open(history_path, 'w') as f:
        f.write(json.dumps({"project": "/test", "sessionId": "third"}) + "\n")

    # Should detect truncation and re-read from start
    result = find_session_for_project("/test", history_path)
    assert result == "third"

    history_path.unlink()

def test_malformed_json_handling():
    """Test that malformed JSON lines are skipped."""
    reset_history_cache()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)
        f.write(json.dumps({"project": "/test", "sessionId": "first"}) + "\n")
        f.write("not valid json\n")
        f.write(json.dumps({"project": "/test", "sessionId": "second"}) + "\n")
        f.flush()

        result = find_session_for_project("/test", history_path)
        assert result == "second"

    history_path.unlink()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_history_reader.py -v
```

Expected: FAIL with "No module named 'telegram_bridge.history_reader'"

**Step 3: Write implementation with truncation detection**

```python
# src/telegram_bridge/history_reader.py
"""Read session info from Claude's history.jsonl with incremental reading."""
import json
from pathlib import Path

HISTORY_PATH = Path.home() / ".claude" / "history.jsonl"

# State for incremental reading
_last_size = 0
_last_mtime = 0
_session_cache: dict[str, str] = {}  # cwd -> session_id


def find_session_for_project(cwd: str, history_path: Path = HISTORY_PATH) -> str | None:
    """Find the most recent session_id for a project by cwd.

    Uses incremental reading - only reads new lines since last check.
    Detects file truncation and resets cache when needed.
    """
    global _last_size, _last_mtime, _session_cache

    if not history_path.exists():
        return _session_cache.get(cwd)

    try:
        stat = history_path.stat()
        current_size = stat.st_size
        current_mtime = stat.st_mtime

        # Quick mtime check - no changes
        if current_mtime == _last_mtime and current_size == _last_size:
            return _session_cache.get(cwd)

        # File truncated/recreated - reset cache and re-read from start
        if current_size < _last_size:
            _last_size = 0
            _session_cache.clear()

        # Read only new content
        if current_size > _last_size:
            with open(history_path, 'r') as f:
                f.seek(_last_size)
                new_content = f.read()
            _last_size = current_size

            # Parse new lines and update cache
            for line in new_content.splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    project = entry.get("project")
                    session_id = entry.get("sessionId")
                    if project and session_id:
                        _session_cache[project] = session_id
                except json.JSONDecodeError:
                    continue  # Skip malformed lines

        _last_mtime = current_mtime
        return _session_cache.get(cwd)

    except Exception:
        return _session_cache.get(cwd)


def reset_history_cache() -> None:
    """Reset cache (for testing)."""
    global _last_size, _last_mtime, _session_cache
    _last_size = 0
    _last_mtime = 0
    _session_cache = {}
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_history_reader.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/history_reader.py tests/test_history_reader.py
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add history_reader with truncation detection

- Incremental reading: only reads new lines since last check
- Truncation detection: resets cache when file size decreases
- Malformed JSON handling: skips broken lines
- Zero config: works for all sessions without hooks

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add compute_jsonl_path utility

**Files:**
- Modify: `src/telegram_bridge/history_reader.py`
- Test: `tests/test_history_reader.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_history_reader.py
from telegram_bridge.history_reader import compute_jsonl_path

def test_compute_jsonl_path():
    result = compute_jsonl_path("/home/user/dev/my-project", "abc-123-def")
    expected = Path.home() / ".claude" / "projects" / "-home-user-dev-my-project" / "abc-123-def.jsonl"
    assert result == expected

def test_compute_jsonl_path_root():
    result = compute_jsonl_path("/", "test-session")
    expected = Path.home() / ".claude" / "projects" / "-" / "test-session.jsonl"
    assert result == expected
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_history_reader.py::test_compute_jsonl_path -v
```

Expected: FAIL with "cannot import name 'compute_jsonl_path'"

**Step 3: Write implementation**

```python
# Add to src/telegram_bridge/history_reader.py

def compute_jsonl_path(cwd: str, session_id: str) -> Path:
    """Compute jsonl path from cwd and session_id.

    Formula: ~/.claude/projects/{cwd.replace("/", "-")}/{session_id}.jsonl
    """
    project_hash = cwd.replace("/", "-")
    return Path.home() / ".claude" / "projects" / project_hash / f"{session_id}.jsonl"
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_history_reader.py::test_compute_jsonl_path -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/history_reader.py tests/test_history_reader.py
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add compute_jsonl_path utility

Formula: ~/.claude/projects/{cwd.replace("/", "-")}/{session_id}.jsonl

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add tmux discovery functions

**Files:**
- Modify: `src/telegram_bridge/tmux.py`
- Test: `tests/test_tmux.py`

**Step 1: Write the failing test**

```python
# tests/test_tmux.py (append to existing or create)
from telegram_bridge.tmux import find_all_tmux_by_cwd, find_tmux_by_convention

def test_find_all_tmux_by_cwd_single(mocker):
    # Mock subprocess to return one matching session
    mocker.patch('subprocess.run', return_value=mocker.Mock(
        returncode=0,
        stdout="claude-project /home/user/project\n"
    ))

    result = find_all_tmux_by_cwd("/home/user/project")
    assert result == ["claude-project"]

def test_find_all_tmux_by_cwd_multiple(mocker):
    # Mock subprocess to return multiple sessions
    mocker.patch('subprocess.run', return_value=mocker.Mock(
        returncode=0,
        stdout="claude-1 /home/user/project\nother /other/path\nclaude-2 /home/user/project\n"
    ))

    result = find_all_tmux_by_cwd("/home/user/project")
    assert sorted(result) == ["claude-1", "claude-2"]

def test_find_all_tmux_by_cwd_not_found(mocker):
    # Mock subprocess to return no matching sessions
    mocker.patch('subprocess.run', return_value=mocker.Mock(
        returncode=0,
        stdout="other /other/path\n"
    ))

    result = find_all_tmux_by_cwd("/home/user/project")
    assert result == []

def test_find_tmux_by_convention_found(mocker):
    # Mock TmuxSession.exists() to return True
    mocker.patch('telegram_bridge.tmux.TmuxSession.exists', return_value=True)

    result = find_tmux_by_convention("my-project")
    assert result == "claude-my-project"

def test_find_tmux_by_convention_fallback(mocker):
    # Mock first pattern not found, second found
    exists_mock = mocker.patch('telegram_bridge.tmux.TmuxSession.exists')
    exists_mock.side_effect = [False, True]

    result = find_tmux_by_convention("my-project")
    assert result == "my-project"

def test_find_tmux_by_convention_not_found(mocker):
    mocker.patch('telegram_bridge.tmux.TmuxSession.exists', return_value=False)

    result = find_tmux_by_convention("my-project")
    assert result is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_tmux.py -v
```

Expected: FAIL with "cannot import name 'find_all_tmux_by_cwd'"

**Step 3: Write implementation**

```python
# Add to src/telegram_bridge/tmux.py

def find_all_tmux_by_cwd(cwd: str) -> list[str]:
    """Find all tmux sessions with panes in the given cwd.

    Returns list of session names (may be empty).
    """
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{session_name} #{pane_current_path}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        sessions = set()
        for line in result.stdout.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                session_name, pane_path = parts
                if pane_path == cwd:
                    sessions.add(session_name)

        return sorted(sessions)
    except Exception:
        return []


def find_tmux_by_convention(project_name: str) -> str | None:
    """Find tmux session by naming convention.

    Tries:
    1. claude-{project_name}
    2. {project_name}

    Returns session name if found, None otherwise.
    """
    for pattern in [f"claude-{project_name}", project_name]:
        # Check if session exists (any cwd, just need valid session)
        t = TmuxSession(pattern, "/tmp")
        if t.exists():
            return pattern
    return None
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_tmux.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/tmux.py tests/test_tmux.py
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add tmux discovery functions

- find_all_tmux_by_cwd: returns all sessions with panes in cwd
- find_tmux_by_convention: tries claude-{name} then {name}

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update ProjectState model

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Update ProjectState dataclass**

```python
# In src/telegram_bridge/session_manager.py

@dataclass
class ProjectState:
    """State for a single project."""
    project_name: str
    chat_id: int | None = None
    cwd: str | None = None

    # Watcher (one active session_id)
    session_id: str | None = None
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = None

    # Poller (one selected tmux)
    tmux_session: str | None = None
    poller_task: asyncio.Task | None = None

    # DEPRECATED fields (for backwards compat during migration)
    # TODO: Remove after migration complete
    @property
    def claude_session_id(self) -> str | None:
        """Alias for session_id (backwards compat)."""
        return self.session_id

    @claude_session_id.setter
    def claude_session_id(self, value: str | None):
        """Alias for session_id (backwards compat)."""
        self.session_id = value
```

**Step 2: Run syntax check**

```bash
python -m py_compile src/telegram_bridge/session_manager.py
```

Expected: No output (success)

**Step 3: Commit**

```bash
git add src/telegram_bridge/session_manager.py
git commit -m "$(cat <<'EOF'
refactor(telegram-bridge): simplify ProjectState model

- Optional fields instead of dicts (session_id, tmux_session)
- Clear separation: watcher (session_id, jsonl_path) vs poller (tmux_session)
- Backwards compat property for claude_session_id

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add refresh_project_session method

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_session_manager.py or create new
import pytest
from telegram_bridge.session_manager import ProjectManager, ProjectState

def test_refresh_project_session_changes(mocker, tmp_path):
    # Mock history_reader
    mocker.patch(
        'telegram_bridge.session_manager.find_session_for_project',
        return_value="new-session-123"
    )
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.touch()
    mocker.patch(
        'telegram_bridge.session_manager.compute_jsonl_path',
        return_value=jsonl_file
    )

    manager = ProjectManager()
    project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
    project.session_id = "old-session"
    manager.projects["test"] = project

    changed = manager.refresh_project_session(project)

    assert changed is True
    assert project.session_id == "new-session-123"
    assert project.jsonl_path == str(jsonl_file)

def test_refresh_project_session_no_change(mocker):
    mocker.patch(
        'telegram_bridge.session_manager.find_session_for_project',
        return_value="same-session"
    )

    manager = ProjectManager()
    project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
    project.session_id = "same-session"
    manager.projects["test"] = project

    changed = manager.refresh_project_session(project)

    assert changed is False
    assert project.session_id == "same-session"

def test_refresh_project_session_no_cwd(mocker):
    manager = ProjectManager()
    project = ProjectState(project_name="test", cwd=None, chat_id=123)
    manager.projects["test"] = project

    changed = manager.refresh_project_session(project)

    assert changed is False

def test_refresh_project_session_jsonl_not_exists(mocker, tmp_path):
    mocker.patch(
        'telegram_bridge.session_manager.find_session_for_project',
        return_value="new-session"
    )
    # Point to non-existent file
    mocker.patch(
        'telegram_bridge.session_manager.compute_jsonl_path',
        return_value=tmp_path / "nonexistent.jsonl"
    )

    manager = ProjectManager()
    project = ProjectState(project_name="test", cwd="/test/path", chat_id=123)
    manager.projects["test"] = project

    changed = manager.refresh_project_session(project)

    assert changed is True
    assert project.session_id == "new-session"
    assert project.jsonl_path is None  # File doesn't exist
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_session_manager.py::test_refresh_project_session -v
```

Expected: FAIL with "ProjectManager has no attribute 'refresh_project_session'"

**Step 3: Write implementation**

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

    if new_session_id == project.session_id:
        return False  # No change

    # Session changed
    project.session_id = new_session_id

    # Compute jsonl path
    jsonl_path = compute_jsonl_path(project.cwd, new_session_id)
    if jsonl_path.exists():
        project.jsonl_path = str(jsonl_path)
    else:
        project.jsonl_path = None

    return True
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_session_manager.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/session_manager.py tests/test_session_manager.py
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add refresh_project_session method

- Reads latest session_id from history.jsonl
- Computes jsonl_path using formula
- Returns True only if session actually changed

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add HistoryWatcher periodic task

**Files:**
- Create: `src/telegram_bridge/history_watcher.py`
- Test: `tests/test_history_watcher.py`

**Step 1: Write the failing test**

```python
# tests/test_history_watcher.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_history_watcher_detects_session_change():
    """Test that HistoryWatcher detects session changes."""
    from telegram_bridge.history_watcher import HistoryWatcher

    bot = MagicMock()
    start_poller = AsyncMock(return_value=MagicMock())
    start_watcher = AsyncMock(return_value=MagicMock())

    watcher = HistoryWatcher(bot, start_poller, start_watcher)

    # Mock project_manager with a test project
    with patch('telegram_bridge.history_watcher.project_manager') as mock_pm:
        mock_project = MagicMock()
        mock_project.chat_id = 123
        mock_project.cwd = "/test/path"
        mock_project.session_id = "old-session"
        mock_project.watcher_task = None
        mock_pm.projects = {"test": mock_project}
        mock_pm.refresh_project_session.return_value = True  # Session changed

        with patch('telegram_bridge.history_watcher.HISTORY_PATH') as mock_path:
            mock_path.exists.return_value = True
            mock_path.stat.return_value.st_mtime = 12345

            await watcher._check_for_changes()

            # Should have called refresh and _maybe_start_tasks
            mock_pm.refresh_project_session.assert_called_once_with(mock_project)
            mock_pm._maybe_start_tasks.assert_called_once()

@pytest.mark.asyncio
async def test_history_watcher_skips_when_no_change():
    """Test that HistoryWatcher skips when mtime unchanged."""
    from telegram_bridge.history_watcher import HistoryWatcher

    bot = MagicMock()
    watcher = HistoryWatcher(bot, AsyncMock(), AsyncMock())
    watcher._last_mtime = 12345  # Same as we'll return

    with patch('telegram_bridge.history_watcher.HISTORY_PATH') as mock_path:
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_mtime = 12345

        with patch('telegram_bridge.history_watcher.project_manager') as mock_pm:
            await watcher._check_for_changes()

            # Should not have called refresh
            mock_pm.refresh_project_session.assert_not_called()

@pytest.mark.asyncio
async def test_history_watcher_restarts_watcher_on_change():
    """Test that old watcher is cancelled when session changes."""
    from telegram_bridge.history_watcher import HistoryWatcher

    bot = MagicMock()
    start_poller = AsyncMock()
    start_watcher = AsyncMock()

    watcher = HistoryWatcher(bot, start_poller, start_watcher)

    with patch('telegram_bridge.history_watcher.project_manager') as mock_pm:
        # Setup project with existing watcher
        old_watcher_task = MagicMock()
        mock_project = MagicMock()
        mock_project.chat_id = 123
        mock_project.cwd = "/test/path"
        mock_project.session_id = "old-session"
        mock_project.watcher_task = old_watcher_task
        mock_pm.projects = {"test": mock_project}
        mock_pm.refresh_project_session.return_value = True

        with patch('telegram_bridge.history_watcher.HISTORY_PATH') as mock_path:
            mock_path.exists.return_value = True
            mock_path.stat.return_value.st_mtime = 12345

            await watcher._check_for_changes()

            # Should have cancelled old watcher
            old_watcher_task.cancel.assert_called_once()
            assert mock_project.watcher_task is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_history_watcher.py -v
```

Expected: FAIL with "No module named 'telegram_bridge.history_watcher'"

**Step 3: Write implementation**

```python
# src/telegram_bridge/history_watcher.py
"""Periodic watcher for history.jsonl changes."""
import asyncio
from pathlib import Path
from aiogram import Bot

from .session_manager import project_manager, ProjectState
from .history_reader import HISTORY_PATH

REFRESH_INTERVAL = 15  # seconds


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

            old_session = project.session_id
            changed = project_manager.refresh_project_session(project)

            if changed:
                print(f"HistoryWatcher: session changed for {project.project_name}: {old_session} -> {project.session_id}")

                # Start new watcher BEFORE stopping old (avoid message loss)
                old_watcher = project.watcher_task
                await project_manager._maybe_start_tasks(
                    project, self.start_poller, self.start_watcher
                )
                if old_watcher:
                    old_watcher.cancel()


async def create_history_watcher(bot: Bot, start_poller, start_watcher) -> HistoryWatcher:
    """Create and start history watcher."""
    watcher = HistoryWatcher(bot, start_poller, start_watcher)
    await watcher.start()
    return watcher
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_history_watcher.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/history_watcher.py tests/test_history_watcher.py
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add HistoryWatcher periodic task

- Polls history.jsonl every 15s for changes
- Detects session changes and restarts watcher automatically
- mtime optimization: skips if file unchanged

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update /start command with two-phase discovery

**Files:**
- Modify: `src/telegram_bridge/bot.py` (or wherever /start handler is)

**Step 1: Rewrite /start handler**

```python
# In /start handler

@router.message(Command("start"))
async def handle_start(message: Message):
    """Start command - setup project and discover tmux + session."""
    # ... existing permission checks ...

    # Parse args
    if len(args) < 2:
        await message.answer("Usage: /start <project_name> <cwd>")
        return

    project_name = args[0]
    cwd = args[1]

    # Save to config
    project = project_manager.get_or_create(project_name)
    project.chat_id = message.chat.id
    project.cwd = cwd

    # Phase 1: Discover tmux (for poller)
    from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
    tmux_list = find_all_tmux_by_cwd(cwd)

    if len(tmux_list) == 0:
        # Fallback to convention
        tmux_by_convention = find_tmux_by_convention(project_name)
        if tmux_by_convention:
            project.tmux_session = tmux_by_convention
            await message.answer(f"Found tmux by convention: {tmux_by_convention}")
        else:
            await message.answer(f"Claude not found in tmux for {cwd}")
            return
    elif len(tmux_list) == 1:
        project.tmux_session = tmux_list[0]
        await message.answer(f"Connected to tmux: {tmux_list[0]}")
    else:
        # Multiple tmux - show selection UI (future work)
        await message.answer(
            f"Multiple tmux sessions found:\n" +
            "\n".join(f"- {t}" for t in tmux_list) +
            f"\n\nUsing first: {tmux_list[0]}"
        )
        project.tmux_session = tmux_list[0]

    # Phase 2: Discover session_id (for watcher)
    changed = project_manager.refresh_project_session(project)
    if project.session_id:
        await message.answer(f"Found session: {project.session_id[:8]}...")
    else:
        await message.answer("No active Claude session found (will auto-discover when you send message)")

    # Start tasks
    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)

    project_manager._save()
```

**Step 2: Test manually**

Start bot and test /start command.

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "$(cat <<'EOF'
refactor(telegram-bridge): two-phase discovery in /start

Phase 1 (tmux): find_all_tmux_by_cwd -> selection/convention
Phase 2 (session): refresh_project_session from history.jsonl

Independent discoveries, no coupling between tmux and session_id.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Simplify restore_projects

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Rewrite restore_projects**

```python
async def restore_projects(self, start_poller, start_watcher) -> None:
    """Restore sessions from history.jsonl after bot restart."""
    from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention

    for project in self.projects.values():
        if not project.chat_id or not project.cwd:
            continue

        # 1. Find session_id from history.jsonl
        self.refresh_project_session(project)

        # 2. Find tmux by cwd or convention
        if not project.tmux_session:
            tmux_list = find_all_tmux_by_cwd(project.cwd)
            if len(tmux_list) == 1:
                project.tmux_session = tmux_list[0]
            elif len(tmux_list) == 0:
                # Fallback to convention
                tmux_by_convention = find_tmux_by_convention(project.project_name)
                if tmux_by_convention:
                    project.tmux_session = tmux_by_convention

        # 3. Start tasks if ready
        await self._maybe_start_tasks(project, start_poller, start_watcher)

    self._save()
```

**Step 2: Run existing tests**

```bash
pytest tests/ -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add src/telegram_bridge/session_manager.py
git commit -m "$(cat <<'EOF'
refactor(telegram-bridge): simplify restore_projects

- Uses refresh_project_session for session_id discovery
- Independent tmux discovery (cwd or convention)
- No hooks, no HTTP, just history.jsonl

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Remove hook-related code

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Remove methods**

Delete:
- `update_from_hook`
- `handle_session_end`
- `get_by_session`

**Step 2: Update _save to remove sessions**

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

```bash
python -m py_compile src/telegram_bridge/session_manager.py
```

Expected: No output

**Step 4: Commit**

```bash
git add src/telegram_bridge/session_manager.py
git commit -m "$(cat <<'EOF'
refactor(telegram-bridge): remove hook-related code

Deleted:
- update_from_hook
- handle_session_end
- get_by_session
- sessions from config

All session discovery now via history.jsonl.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Remove HTTP server

**Files:**
- Modify: `src/telegram_bridge/main.py`
- Modify: `src/telegram_bridge/config.py`

**Step 1: Remove HTTP code from main.py**

Delete:
- `handle_register`
- `handle_unregister`
- `handle_debug`
- `run_http_server`
- `from aiohttp import web` import

**Step 2: Update main() function**

```python
# src/telegram_bridge/main.py
import asyncio
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router
from .session_manager import project_manager, ProjectState

async def main():
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Starting Telegram Bridge (history.jsonl mode)")
    print(f"Admin IDs: {settings.get_admin_ids()}")
    print(f"Base dir: {settings.base_dir}")

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Start Claude / show status"),
        BotCommand(command="restart_session", description="Restart Claude session"),
        BotCommand(command="my_chat_id", description="Show your user ID"),
        BotCommand(command="esc", description="Send Escape to Claude"),
    ])

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

    print("History watcher started (15s polling)")

    # Start Telegram polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: Remove http_port from config.py**

```python
# In src/telegram_bridge/config.py
# Remove http_port field from Settings class
```

**Step 4: Update default_config**

```python
def default_config() -> dict:
    return {"projects": {}}
```

**Step 5: Run syntax check**

```bash
python -m py_compile src/telegram_bridge/main.py src/telegram_bridge/config.py
```

Expected: No output

**Step 6: Commit**

```bash
git add src/telegram_bridge/main.py src/telegram_bridge/config.py
git commit -m "$(cat <<'EOF'
refactor(telegram-bridge): remove HTTP server completely

- No /session/register, /session/unregister endpoints
- No /debug endpoint
- No http_port config
- All session management via history.jsonl polling

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Deprecate hooks

**Files:**
- Modify: `hooks/session-start.sh`
- Modify: `hooks/session-end.sh`

**Step 1: Add deprecation notice**

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
git commit -m "$(cat <<'EOF'
deprecate(telegram-bridge): mark hooks as no longer needed

Hooks replaced by history.jsonl polling.
Users can remove from ~/.claude/settings.json.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Add cleanup logic

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Add should_cleanup helper**

```python
# Add to session_manager.py
import time

def should_cleanup_project(project: ProjectState) -> bool:
    """Check if project should be cleaned up (inactive > 30 days).

    Uses jsonl file mtime, not last_activity tracking.
    """
    if not project.jsonl_path:
        return True  # No jsonl = cleanup

    jsonl_path = Path(project.jsonl_path)
    if not jsonl_path.exists():
        return True  # File deleted

    try:
        mtime = jsonl_path.stat().st_mtime
        age_days = (time.time() - mtime) / 86400
        return age_days > 30
    except Exception:
        return True  # Error = cleanup
```

**Step 2: Apply cleanup in restore_projects**

```python
async def restore_projects(self, start_poller, start_watcher) -> None:
    """Restore sessions from history.jsonl after bot restart."""
    from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention

    for project in list(self.projects.values()):  # Copy to allow removal
        if not project.chat_id or not project.cwd:
            continue

        # 1. Find session_id from history.jsonl
        self.refresh_project_session(project)

        # Check if should cleanup
        if should_cleanup_project(project):
            print(f"Cleaning up inactive project: {project.project_name}")
            del self.projects[project.project_name]
            continue

        # 2. Find tmux by cwd or convention
        if not project.tmux_session:
            tmux_list = find_all_tmux_by_cwd(project.cwd)
            if len(tmux_list) == 1:
                project.tmux_session = tmux_list[0]
            elif len(tmux_list) == 0:
                tmux_by_convention = find_tmux_by_convention(project.project_name)
                if tmux_by_convention:
                    project.tmux_session = tmux_by_convention

        # 3. Start tasks if ready
        await self._maybe_start_tasks(project, start_poller, start_watcher)

    self._save()
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/session_manager.py
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add cleanup by jsonl mtime

- Cleanup projects with jsonl inactive > 30 days
- No last_activity tracking needed
- Applied during restore_projects

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Integration testing

**Manual testing checklist:**

```bash
# 1. Restart bot
/home/superbereza/dev/personal-agent/agent-tools/telegram-bridge/restart.sh

# 2. Check bot logs
tail -50 /home/superbereza/dev/personal-agent/tmp/telegram-bridge-logs/bot.log

# Expected: "Starting Telegram Bridge (history.jsonl mode)", "History watcher started", no errors

# 3. Test /start in Telegram
# Send: /start <project_name> <cwd>
# Expected: Connects to tmux and session without hooks

# 4. Test watcher
# Send message in Claude
# Expected: Appears in Telegram within 2s

# 5. Test session change detection
# In Claude: run /resume or /new
# Wait 15-20 seconds
# Send message in Claude
# Expected: Appears in Telegram (watcher auto-reconnected)
# Check logs for: "HistoryWatcher: session changed"

# 6. Test truncated file handling
# Simulate: truncate ~/.claude/history.jsonl (backup first!)
# Expected: Bot continues working, no crashes

# 7. Test multiple tmux sessions
# Create second tmux with same cwd
# Run /start
# Expected: Shows selection or uses first

# 8. Test restore after restart
# Restart bot
# Expected: Auto-restores session from history.jsonl
```

---

## Task 14: Update documentation

**Files:**
- Modify: `docs/setup.md`
- Modify: `CLAUDE.md`

**Step 1: Update setup.md**

Remove hook setup instructions. Add:

```markdown
## Zero-Config Mode (Default)

telegram-bridge now works without any Claude configuration:

1. Start bot: `./restart.sh`
2. Send `/start <project_name> <cwd>` in Telegram
3. Done! No hooks, no settings.json edits needed.

The bridge automatically discovers Claude sessions via `~/.claude/history.jsonl`.

### How it works

- **Session discovery**: Polls `~/.claude/history.jsonl` every 15s
- **Tmux discovery**: Scans tmux panes for matching cwd
- **Auto-reconnect**: Detects session changes (/new, /resume, /compact)
- **Cleanup**: Removes projects inactive > 30 days

### Constraints

- One Claude per tmux session (split panes not supported)
- cwd fixed at /start (cd commands not tracked)
- Session changes detected within 15s (not instant)
```

**Step 2: Update CLAUDE.md**

```markdown
## Architecture

**Session discovery:** history.jsonl polling (not hooks)
**Refresh interval:** 15s
**Cleanup threshold:** 30 days (by jsonl mtime)
```

**Step 3: Commit**

```bash
git add docs/setup.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(telegram-bridge): update for history.jsonl architecture

- Removed hook setup instructions
- Added zero-config explanation
- Documented constraints and behavior

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Add logging strategy

**Files:**
- Modify: `src/telegram_bridge/history_watcher.py`
- Modify: `src/telegram_bridge/history_reader.py`
- Modify: `src/telegram_bridge/session_manager.py`

**Step 1: Setup structured logging**

```python
# src/telegram_bridge/logging_config.py
import logging

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

logger = logging.getLogger("telegram_bridge")
```

**Step 2: Add logging to key points**

```python
# In history_watcher.py
logger.info("session_changed", extra={
    "project": project.project_name,
    "old_session": old_session[:8] if old_session else None,
    "new_session": project.session_id[:8] if project.session_id else None,
})

logger.warning("tmux_died", extra={"project": project.project_name, "tmux": project.tmux_session})

# In history_reader.py
logger.debug("history_read", extra={"new_lines": len(new_lines), "cache_size": len(_session_cache)})
logger.warning("json_decode_error", extra={"line": line[:50]})

# In session_manager.py
logger.info("project_restored", extra={"project": project.project_name})
logger.info("project_cleanup", extra={"project": project.project_name, "reason": "inactive_30_days"})
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add structured logging

Key log events:
- session_changed: session_id transition
- tmux_died: tmux session closed
- project_restored: restored from history.jsonl
- project_cleanup: removed inactive project

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Add path sanitization

**Files:**
- Modify: `src/telegram_bridge/history_reader.py`
- Test: `tests/test_history_reader.py`

**Step 1: Write failing tests for edge cases**

```python
# tests/test_history_reader.py

def test_compute_jsonl_path_trailing_slash():
    """Trailing slash should be normalized."""
    result1 = compute_jsonl_path("/home/user/project", "abc")
    result2 = compute_jsonl_path("/home/user/project/", "abc")
    assert result1 == result2

def test_compute_jsonl_path_double_slash():
    """Double slashes should be normalized."""
    result1 = compute_jsonl_path("/home/user/project", "abc")
    result2 = compute_jsonl_path("/home//user//project", "abc")
    assert result1 == result2

def test_compute_jsonl_path_symlink_not_resolved():
    """Symlinks should NOT be resolved (match Claude behavior)."""
    # Claude uses raw cwd, not resolved path
    result = compute_jsonl_path("/home/user/link-to-project", "abc")
    assert "-home-user-link-to-project" in str(result)
```

**Step 2: Update compute_jsonl_path**

```python
def compute_jsonl_path(cwd: str, session_id: str) -> Path:
    """Compute jsonl path from cwd and session_id.

    Formula: ~/.claude/projects/{normalized_cwd.replace("/", "-")}/{session_id}.jsonl

    Normalization:
    - Remove trailing slashes
    - Collapse double slashes
    - Do NOT resolve symlinks (match Claude behavior)
    """
    # Normalize path
    normalized = cwd.rstrip("/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")

    project_hash = normalized.replace("/", "-")
    return Path.home() / ".claude" / "projects" / project_hash / f"{session_id}.jsonl"
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/history_reader.py tests/test_history_reader.py
git commit -m "$(cat <<'EOF'
fix(telegram-bridge): normalize paths in compute_jsonl_path

- Remove trailing slashes
- Collapse double slashes
- Do NOT resolve symlinks (match Claude behavior)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Add cleanup, tmux death check, and notification in periodic refresh

**Files:**
- Modify: `src/telegram_bridge/history_watcher.py`

**Step 1: Add cleanup, tmux check, and notification before session check**

```python
# In history_watcher.py, _check_for_changes method

async def _check_for_changes(self):
    """Check if history.jsonl changed and refresh sessions."""
    if not HISTORY_PATH.exists():
        return

    # Quick mtime check
    mtime = HISTORY_PATH.stat().st_mtime
    if mtime == self._last_mtime:
        return
    self._last_mtime = mtime

    # Check each project
    for project in list(project_manager.projects.values()):
        if not project.chat_id or not project.cwd:
            continue

        # 1. Check if should cleanup (inactive > 30 days)
        if should_cleanup_project(project):
            logger.info(f"Cleaning up inactive project: {project.project_name}")
            if project.watcher_task:
                project.watcher_task.cancel()
            if project.poller_task:
                project.poller_task.cancel()
            del project_manager.projects[project.project_name]
            continue

        # 2. Check if tmux died
        if project.tmux_session:
            from .tmux import TmuxSession
            tmux = TmuxSession(project.tmux_session, project.cwd)
            if not tmux.exists():
                logger.warning(f"tmux died: {project.tmux_session}")
                # Notify user
                await self.bot.send_message(
                    project.chat_id,
                    f"⚠️ Claude session closed (tmux died): {project.project_name}"
                )
                if project.watcher_task:
                    project.watcher_task.cancel()
                    project.watcher_task = None
                if project.poller_task:
                    project.poller_task.cancel()
                    project.poller_task = None
                project.tmux_session = None
                project.session_id = None
                continue

        # 3. Check if session changed
        old_session = project.session_id
        changed = project_manager.refresh_project_session(project)

        if changed:
            logger.info(f"session changed: {old_session[:8] if old_session else None} -> {project.session_id[:8] if project.session_id else None}")

            # Start new before stop old (avoid message loss)
            old_watcher = project.watcher_task
            await project_manager._maybe_start_tasks(project, self.start_poller, self.start_watcher)
            if old_watcher:
                old_watcher.cancel()
```

**Step 2: Commit**

```bash
git add src/telegram_bridge/history_watcher.py
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add cleanup, tmux death check, and notification

- Cleanup projects inactive > 30 days (by jsonl mtime)
- Check if tmux session still exists before refreshing
- Notify user when tmux died (⚠️ message to chat)
- If tmux died, stop watcher and poller
- Start new watcher before stopping old (avoid message loss)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Add error handling policy

**Files:**
- Create: `src/telegram_bridge/errors.py`
- Modify: `src/telegram_bridge/history_reader.py`
- Modify: `src/telegram_bridge/history_watcher.py`

**Step 1: Define error handling policy**

```python
# src/telegram_bridge/errors.py
"""Error handling policy for telegram-bridge.

ERROR level (requires attention):
- Bot startup failures
- Telegram API errors (rate limits, auth failures)
- Config parsing failures

WARNING level (expected, recoverable):
- tmux session died
- jsonl file not found
- JSON decode errors in history.jsonl
- Session not found during refresh

INFO level (normal operations):
- Session changed
- Project restored
- Watcher/poller started/stopped

DEBUG level (troubleshooting):
- File read operations
- Cache updates
- mtime checks
"""

class TelegramBridgeError(Exception):
    """Base exception for telegram-bridge."""
    pass

class ConfigError(TelegramBridgeError):
    """Configuration error."""
    pass

class SessionDiscoveryError(TelegramBridgeError):
    """Session discovery failed."""
    pass
```

**Step 2: Apply policy to history_reader.py**

```python
# In history_reader.py

def find_session_for_project(cwd: str, history_path: Path = HISTORY_PATH) -> str | None:
    """Find the most recent session_id for a project by cwd."""
    global _last_size, _last_mtime, _session_cache

    if not history_path.exists():
        logger.debug("history.jsonl not found")
        return _session_cache.get(cwd)

    try:
        stat = history_path.stat()
        # ... existing code ...
    except PermissionError as e:
        logger.error(f"Permission denied reading history.jsonl: {e}")
        return _session_cache.get(cwd)
    except OSError as e:
        logger.warning(f"OS error reading history.jsonl: {e}")
        return _session_cache.get(cwd)
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add error handling policy

Error levels defined:
- ERROR: startup failures, API errors, config errors
- WARNING: tmux died, file not found, JSON decode errors
- INFO: session changes, project restored
- DEBUG: file reads, cache updates

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: Update permission callback routing to use tmux_session

**Files:**
- Modify: `src/telegram_bridge/permission_poller.py`
- Test: `tests/test_permission_poller.py`

**Context:** Permission callbacks currently use session_id which changes on /new, /resume. Need to use tmux_session instead for stable routing.

**Step 1: Write failing test**

```python
# tests/test_permission_poller.py

def test_permission_callback_uses_tmux_session():
    """Callback data should use tmux_session, not session_id."""
    # When callback is created
    callback_data = f"approve:{tmux_session}"

    # When callback is received
    action, tmux_session_from_callback = callback_data.split(":", 1)
    project = project_manager.get_by_tmux(tmux_session_from_callback)

    assert project is not None
    assert action == "approve"
```

**Step 2: Update callback format**

```python
# In permission_poller.py

# Old format (WRONG - session_id can change):
# callback_data = f"approve:{project.session_id}"

# New format (CORRECT - tmux_session is stable):
callback_data = f"approve:{project.tmux_session}"

# In callback handler:
async def handle_permission_callback(callback: CallbackQuery):
    action, tmux_session = callback.data.split(":", 1)
    project = project_manager.get_by_tmux(tmux_session)
    if not project:
        await callback.answer("Session not found")
        return
    # ... handle action ...
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/permission_poller.py tests/test_permission_poller.py
git commit -m "$(cat <<'EOF'
fix(telegram-bridge): use tmux_session in permission callbacks

- Callback format: {action}:{tmux_session} instead of {action}:{session_id}
- tmux_session is stable across /new, /resume, /compact
- Prevents callback failures when session changes

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 20: Add multiple tmux selection UI

**Files:**
- Modify: `src/telegram_bridge/bot.py`
- Create: `src/telegram_bridge/tmux_selector.py`

**Context:** When multiple tmux sessions match cwd, currently we just take first. Need inline keyboard for user to choose.

**Step 1: Create tmux selector module**

```python
# src/telegram_bridge/tmux_selector.py
"""Handle multiple tmux session selection."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def create_tmux_selection_keyboard(tmux_list: list[str], project_name: str) -> InlineKeyboardMarkup:
    """Create inline keyboard for tmux selection."""
    buttons = [
        [InlineKeyboardButton(
            text=f"📟 {tmux}",
            callback_data=f"select_tmux:{project_name}:{tmux}"
        )]
        for tmux in tmux_list
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def handle_tmux_selection(callback: CallbackQuery, project_manager):
    """Handle tmux selection callback."""
    _, project_name, tmux_session = callback.data.split(":", 2)

    project = project_manager.get_or_create(project_name)
    project.tmux_session = tmux_session

    await callback.message.edit_text(f"✅ Connected to tmux: {tmux_session}")
    await callback.answer()

    return project
```

**Step 2: Update /start to use selection UI**

```python
# In bot.py /start handler

if len(tmux_list) > 1:
    # Multiple tmux - show selection keyboard
    from .tmux_selector import create_tmux_selection_keyboard
    keyboard = create_tmux_selection_keyboard(tmux_list, project_name)
    await message.answer(
        f"Multiple tmux sessions found for {cwd}:\n\n"
        "Select which one to connect:",
        reply_markup=keyboard
    )
    # Don't start tasks yet - wait for selection callback
    project_manager._save()
    return
```

**Step 3: Register callback handler**

```python
# In bot.py

@router.callback_query(F.data.startswith("select_tmux:"))
async def on_tmux_selected(callback: CallbackQuery):
    from .tmux_selector import handle_tmux_selection

    project = await handle_tmux_selection(callback, project_manager)

    # Now start tasks
    project_manager.refresh_project_session(project)
    await project_manager._maybe_start_tasks(project, start_poller, start_watcher)
    project_manager._save()

    if project.session_id:
        await callback.message.answer(f"Found session: {project.session_id[:8]}...")
    else:
        await callback.message.answer("No active Claude session found (will auto-discover)")
```

**Step 4: Commit**

```bash
git add src/telegram_bridge/bot.py src/telegram_bridge/tmux_selector.py
git commit -m "$(cat <<'EOF'
feat(telegram-bridge): add multiple tmux selection UI

- When multiple tmux match cwd, show inline keyboard
- User selects which tmux to connect
- Tasks start only after selection

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Key Changes |
|------|-------------|-------------|
| 1 | HistoryReader | Incremental reading, truncation detection, malformed JSON handling |
| 2 | compute_jsonl_path | Formula: `~/.claude/projects/{cwd.replace("/", "-")}/{session_id}.jsonl` |
| 3 | tmux discovery | find_all_tmux_by_cwd, find_tmux_by_convention |
| 4 | ProjectState model | Optional fields (session_id, tmux_session), clear separation |
| 5 | refresh_project_session | Read session_id from history.jsonl, compute jsonl_path |
| 6 | HistoryWatcher | 15s polling, mtime optimization, auto-restart watcher |
| 7 | /start command | Two-phase discovery: tmux (cwd/convention) + session (history.jsonl) |
| 8 | restore_projects | Simplified, no hooks, uses refresh_project_session |
| 9 | Remove hooks code | Deleted update_from_hook, handle_session_end, get_by_session |
| 10 | Remove HTTP server | No endpoints, no http_port, clean main() |
| 11 | Deprecate hooks | Add notice, exit 0 |
| 12 | Cleanup logic | By jsonl mtime (30 days), no last_activity tracking |
| 13 | Integration test | Manual checklist: restart, /start, watcher, session change |
| 14 | Documentation | Zero-config setup, architecture, constraints |
| 15 | Logging strategy | Structured logging with levels (ERROR/WARNING/INFO/DEBUG) |
| 16 | Path sanitization | Normalize trailing slashes, double slashes |
| 17 | Cleanup + tmux death + notification | Cleanup inactive 30d, stop tasks when tmux dies, notify user |
| 18 | Error handling policy | Define error levels, graceful degradation |
| 19 | Permission callback routing | Use tmux_session instead of session_id in callbacks |
| 20 | Multiple tmux selection UI | Inline keyboard for user to choose tmux session |

**Verification commands:**

```bash
# Run all tests
pytest tests/ -v

# Syntax check all modified files
python -m py_compile src/telegram_bridge/*.py

# Integration test
./restart.sh && tail -f tmp/telegram-bridge-logs/bot.log
```

**Key design points implemented:**

- ✅ Optional fields (session_id, tmux_session) instead of dicts
- ✅ Terminology: tmux_session vs session_id
- ✅ jsonl_path formula with compute_jsonl_path
- ✅ Truncation detection (size < last_size)
- ✅ Cleanup by jsonl mtime (not last_activity)
- ✅ Constraints documented
- ✅ Two-phase discovery in /start (independent tmux + session)
- ✅ 15s refresh interval
- ✅ mtime optimization (skip if unchanged)
- ✅ Tmux death detection (stop tasks when tmux dies)
- ✅ Start new watcher before stop old (avoid message loss)
- ✅ Structured logging with error policy
- ✅ Path normalization for edge cases
- ✅ Tmux death notification to user
- ✅ Periodic cleanup of inactive projects (30 days)
- ✅ Permission callback uses tmux_session (stable)
- ✅ Multiple tmux selection UI (inline keyboard)
