# Session Binding Race Condition Fix - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix race condition where new thread can bind to wrong session during /start

**Architecture:** Filter sessions by creation time - only consider sessions created AFTER /start was pressed. Two binding paths exist and BOTH must be fixed.

**Tech Stack:** Python, asyncio, JSON

**Design:** [session-binding-race-fix](../designs/done/2025-12-29-session-binding-race-fix.md)

---

## Layer-Based Refactoring Compatibility

This plan modifies files that will be restructured in [bot-refactoring](../designs/2025-12-27-bot-refactoring/00-overview.md):

| Current Location | After Refactoring | Notes |
|------------------|-------------------|-------|
| `history_reader.py` | `adapters/history.py` | `get_session_creation_time` is adapter function |
| `session_manager.py:ThreadInfo` | `domain/models.py` | `start_requested_at` is domain field |
| `history_watcher.py` | Not touched (separate task) | No conflicts |
| `launch_animation.py` | `services/launch.py` | Already extracted, changes stay |
| `bot.py:_send_session_command` | `handlers/sessions.py` | Changes migrate with function |

---

## Background: Two Binding Paths

There are TWO code paths that bind sessions to threads:

1. **`poll_for_session_thread`** (history_watcher.py:244)
   - Called when: `thread.session_id is None` and user sends message
   - Uses: `find_session_by_user_message()` - matches by message text
   - Trigger: bot.py:1436

2. **`_bind_awaiting_threads`** (history_watcher.py:124)
   - Called when: `thread.awaiting_new_session = True`
   - Uses: `find_session_for_project()` - gets latest session
   - Trigger: `/new`, `/clear` commands, `/start` in thread

**BOTH paths must filter by session creation time!**

---

### Task 1: Add `get_session_creation_time` function

**Files:**
- Modify: `src/codogram/history_reader.py` (after line 131)
- Test: `tests/test_history_reader.py`

**Step 1: Write tests**

Add to `tests/test_history_reader.py`:

```python
import time

def test_get_session_creation_time():
    """Test reading session creation time from first entry timestamp."""
    from codogram.history_reader import get_session_creation_time

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "test-session.jsonl"
        timestamp = 1703847600.123  # Fixed timestamp for test

        with open(jsonl_path, 'w') as f:
            f.write(json.dumps({"type": "system", "timestamp": timestamp}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": timestamp + 1}) + "\n")

        result = get_session_creation_time(jsonl_path)
        assert result == timestamp


def test_get_session_creation_time_missing_file():
    """Return 0 for missing file."""
    from codogram.history_reader import get_session_creation_time

    result = get_session_creation_time(Path("/nonexistent/path.jsonl"))
    assert result == 0


def test_get_session_creation_time_empty_file():
    """Return 0 for empty file."""
    from codogram.history_reader import get_session_creation_time

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "empty.jsonl"
        jsonl_path.touch()

        result = get_session_creation_time(jsonl_path)
        assert result == 0


def test_get_session_creation_time_no_timestamp():
    """Return 0 if first entry has no timestamp field."""
    from codogram.history_reader import get_session_creation_time

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "no-ts.jsonl"
        with open(jsonl_path, 'w') as f:
            f.write(json.dumps({"type": "system"}) + "\n")

        result = get_session_creation_time(jsonl_path)
        assert result == 0


def test_get_session_creation_time_malformed_json():
    """Return 0 for malformed JSON."""
    from codogram.history_reader import get_session_creation_time

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "bad.jsonl"
        with open(jsonl_path, 'w') as f:
            f.write("not valid json\n")

        result = get_session_creation_time(jsonl_path)
        assert result == 0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_history_reader.py::test_get_session_creation_time -v
```
Expected: FAIL with "cannot import name 'get_session_creation_time'"

**Step 3: Implement**

Add to `src/codogram/history_reader.py` after `get_last_user_message_from_jsonl`:

```python
def get_session_creation_time(jsonl_path: Path) -> float:
    """Get timestamp of first entry in session jsonl.

    This is more reliable than st_mtime/st_ctime because:
    - st_mtime updates on every write
    - st_ctime is inode change time, not creation time (Linux)
    - First entry timestamp IS the session creation time

    Returns 0 if file doesn't exist, is empty, or can't be read.
    """
    if not jsonl_path.exists():
        return 0

    try:
        with open(jsonl_path, 'r') as f:
            first_line = f.readline()
            if first_line.strip():
                entry = json.loads(first_line)
                return entry.get("timestamp", 0)
        return 0
    except (json.JSONDecodeError, OSError):
        return 0
```

**Step 4: Run all tests**

```bash
pytest tests/test_history_reader.py -v -k "get_session_creation_time"
```
Expected: 5 tests PASS

**Step 5: Commit**

```bash
git add src/codogram/history_reader.py tests/test_history_reader.py
git commit -m "feat(history): add get_session_creation_time function"
```

---

### Task 2: Add `start_requested_at` field to ThreadInfo with persistence

**Files:**
- Modify: `src/codogram/session_manager.py:99` (ThreadInfo)
- Modify: `src/codogram/session_manager.py:172` (_load_projects)
- Modify: `src/codogram/session_manager.py:208` (_save)
- Test: `tests/test_session_manager.py`

**Step 1: Write tests**

Add to `tests/test_session_manager.py`:

```python
def test_thread_info_start_requested_at_default():
    """Test start_requested_at defaults to None."""
    from codogram.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="test")
    assert thread.start_requested_at is None


def test_thread_info_start_requested_at_assignment():
    """Test start_requested_at can be set."""
    from codogram.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="test")
    thread.start_requested_at = 1703847600.123
    assert thread.start_requested_at == 1703847600.123


def test_start_requested_at_persistence(tmp_path, monkeypatch):
    """Test start_requested_at survives save/load cycle."""
    from codogram.session_manager import ProjectManager, ThreadInfo
    from codogram import config

    # Use temp config file
    config_file = tmp_path / ".config.json"
    monkeypatch.setattr(config, 'CONFIG_PATH', config_file)

    # Create manager and add project with thread
    pm = ProjectManager()
    project = pm.get_or_create("test-project")
    project.chat_id = 12345
    project.cwd = "/test/path"

    thread = project.get_or_create_thread(100, "test-thread")
    thread.start_requested_at = 1703847600.5
    thread.awaiting_new_session = True

    pm._save()

    # Create new manager (simulates restart)
    pm2 = ProjectManager()
    project2 = pm2.projects.get("test-project")
    thread2 = project2.threads.get(100)

    assert thread2.start_requested_at == 1703847600.5
    assert thread2.awaiting_new_session is True
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_session_manager.py::test_thread_info_start_requested_at_default -v
```
Expected: FAIL with "no attribute 'start_requested_at'"

**Step 3: Implement**

In `src/codogram/session_manager.py`:

**3a.** Add field to ThreadInfo (after line 99, after `awaiting_new_session`):

```python
    # For session binding race condition fix:
    start_requested_at: float | None = None
```

**3b.** Load in `_load_projects` (around line 172, add to ThreadInfo creation):

```python
                        start_requested_at=thread_data.get("start_requested_at"),
```

**3c.** Save in `_save` (around line 208, add to thread dict):

```python
                        "start_requested_at": t.start_requested_at,
```

**Step 4: Run all tests**

```bash
pytest tests/test_session_manager.py -v -k "start_requested_at"
```
Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat(session): add start_requested_at field with persistence"
```

---

### Task 3: Add `created_after` to `find_session_by_user_message`

**Files:**
- Modify: `src/codogram/history_reader.py:152-178`
- Test: `tests/test_history_reader.py`

**Step 1: Write test**

Add to `tests/test_history_reader.py`:

```python
def test_find_session_by_user_message_filters_by_created_after(tmp_path, monkeypatch):
    """Test that created_after filters out old sessions."""
    from codogram.history_reader import find_session_by_user_message

    # Create project directory structure
    project_dir = tmp_path / ".claude" / "projects" / "-test-cwd"
    project_dir.mkdir(parents=True)

    # Old session (created at t=100)
    old_session = project_dir / "old-session.jsonl"
    with open(old_session, 'w') as f:
        f.write(json.dumps({"type": "system", "timestamp": 100}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n")

    # New session (created at t=200)
    new_session = project_dir / "new-session.jsonl"
    with open(new_session, 'w') as f:
        f.write(json.dumps({"type": "system", "timestamp": 200}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n")

    # Patch Path.home using monkeypatch (proper pytest way)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)

    # Without filter: should find new-session (newest by mtime)
    result = find_session_by_user_message("/test/cwd", "Hello")
    assert result is not None
    session_id, _ = result
    assert session_id == "new-session"

    # With created_after=150: should find new-session (created at 200 > 150)
    result = find_session_by_user_message("/test/cwd", "Hello", created_after=150)
    assert result is not None
    session_id, _ = result
    assert session_id == "new-session"

    # With created_after=250: should find nothing (both too old)
    result = find_session_by_user_message("/test/cwd", "Hello", created_after=250)
    assert result is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_history_reader.py::test_find_session_by_user_message_filters_by_created_after -v
```
Expected: FAIL with "unexpected keyword argument 'created_after'"

**Step 3: Implement**

Modify `find_session_by_user_message` in `src/codogram/history_reader.py`:

```python
def find_session_by_user_message(
    cwd: str,
    user_message: str,
    created_after: float | None = None,
) -> tuple[str, Path] | None:
    """Find session that contains the given user message.

    Scans ALL session jsonl files for a cwd (not just the latest).

    Args:
        cwd: Project working directory
        user_message: Last user message to match
        created_after: Only consider sessions created after this timestamp.
                       Used to prevent binding to old sessions during /start.

    Returns (session_id, jsonl_path) or None if not found.
    """
    # Compute project directory
    normalized = cwd.rstrip("/") or "/"
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    project_hash = normalized.replace("/", "-")
    project_dir = Path.home() / ".claude" / "projects" / project_hash

    if not project_dir.exists():
        return None

    # Scan all jsonl files, sorted by mtime (newest first)
    jsonl_files = list(project_dir.glob("*.jsonl"))
    jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for jsonl_path in jsonl_files:
        # Filter by creation time if specified
        if created_after is not None:
            session_created = get_session_creation_time(jsonl_path)
            if session_created < created_after:
                continue  # Session created before /start — skip

        last_msg = get_last_user_message_from_jsonl(jsonl_path)
        if last_msg == user_message:
            session_id = jsonl_path.stem
            return (session_id, jsonl_path)

    return None
```

**Step 4: Run test**

```bash
pytest tests/test_history_reader.py::test_find_session_by_user_message_filters_by_created_after -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/history_reader.py tests/test_history_reader.py
git commit -m "feat(history): add created_after filter to find_session_by_user_message"
```

---

### Task 4: Fix Path 1 - `poll_for_session_thread`

**Files:**
- Modify: `src/codogram/history_watcher.py:281`

**Step 1: Locate**

Find the call to `find_session_by_user_message` in `poll_for_session_thread` (line 281):

```python
result = find_session_by_user_message(project.cwd, thread.last_sent_message)
```

**Step 2: Modify**

Change to:

```python
result = find_session_by_user_message(
    project.cwd,
    thread.last_sent_message,
    created_after=thread.start_requested_at,
)
```

**Step 3: Clear after bind**

After successful binding (around line 291), add clearing after `thread.awaiting_new_session = False`:

```python
thread.start_requested_at = None
```

**Step 4: Run tests**

```bash
pytest tests/test_history_watcher.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "fix(watcher): filter by created_after in poll_for_session_thread"
```

---

### Task 5: Fix Path 2 - `_bind_awaiting_threads`

**Files:**
- Modify: `src/codogram/history_watcher.py:124-146`

**Step 1: Locate**

Find `_bind_awaiting_threads` method (line 124).

**Step 2: Add creation time filter**

Add import at top of method and filter before binding:

```python
async def _bind_awaiting_threads(self, project: ProjectState):
    """Find new sessions and bind to awaiting threads.

    NOTE: Binds only ONE thread per cycle to prevent race condition where
    multiple awaiting threads bind to the same session.
    """
    from .history_reader import find_session_for_project, compute_jsonl_path, get_session_creation_time

    # Get latest session once
    new_session = find_session_for_project(project.cwd)
    if not new_session:
        return

    # Find first awaiting thread that can bind to this session
    for thread in project.threads.values():
        if not thread.awaiting_new_session:
            continue
        if thread.session_id == new_session:
            continue  # Already has this session

        # Filter by creation time to prevent race condition
        if thread.start_requested_at:
            jsonl_path = compute_jsonl_path(project.cwd, new_session)
            session_created = get_session_creation_time(jsonl_path)
            if session_created < thread.start_requested_at:
                logger.debug(
                    f"skip_old_session: thread={thread.name}, "
                    f"session_created={session_created}, start_requested={thread.start_requested_at}"
                )
                continue  # Session created before /start — skip

        # Bind ONE thread and exit - next cycle will handle others
        await self._bind_thread_to_session(project, thread, new_session)
        return
```

**Step 3: Run tests**

```bash
pytest tests/test_history_watcher.py -v
```
Expected: PASS

**Step 4: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "fix(watcher): filter by created_after in _bind_awaiting_threads"
```

---

### Task 6: Clear `start_requested_at` in `_bind_thread_to_session`

**Files:**
- Modify: `src/codogram/history_watcher.py:171`

**Step 1: Locate**

In `_bind_thread_to_session`, find where `awaiting_new_session` is cleared (line 171):

```python
thread.awaiting_new_session = False
```

**Step 2: Add clearing**

Add after that line:

```python
thread.start_requested_at = None
```

**Step 3: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "fix(watcher): clear start_requested_at in _bind_thread_to_session"
```

---

### Task 7: Set `start_requested_at` in `/start` flow

**Files:**
- Modify: `src/codogram/launch_animation.py:75`

**NOTE:** `launch_animation.py` already has `import time` (line 5).

**Step 1: Set timestamp in launch_with_animation**

In `launch_with_animation`, after `thread.awaiting_new_session = True` (line 75):

```python
thread.start_requested_at = time.time()
```

Full context:
```python
try:
    thread.awaiting_new_session = True
    thread.start_requested_at = time.time()  # ADD THIS
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/launch_animation.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/launch_animation.py
git commit -m "feat(launch_animation): set start_requested_at when launching Claude"
```

---

### Task 8: Set `start_requested_at` in `/new` and `/clear`

**Files:**
- Modify: `src/codogram/bot.py:3` (imports)
- Modify: `src/codogram/bot.py:866` (_send_session_command)

**Background:**

`/new` and `/clear` commands also set `awaiting_new_session = True` via `_send_session_command`. Without setting `start_requested_at`, the time filter in `_bind_awaiting_threads` will be skipped (because `if thread.start_requested_at:` is False).

**Step 1: Add import time**

Add `import time` at top of `bot.py` (around line 3, after `from pathlib import Path`):

```python
import time
```

**Step 2: Locate _send_session_command (around line 866)**

```python
# Mark thread as awaiting new session
thread.awaiting_new_session = True
thread.last_sent_message = None
project_manager._save()
```

**Step 3: Add start_requested_at**

After `thread.awaiting_new_session = True`, add:

```python
thread.start_requested_at = time.time()
```

Full context:
```python
# Mark thread as awaiting new session
thread.awaiting_new_session = True
thread.start_requested_at = time.time()  # ADD THIS
thread.last_sent_message = None
project_manager._save()
```

**Step 4: Verify syntax**

Run: `python3 -m py_compile src/codogram/bot.py`
Expected: No errors

**Step 5: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): set start_requested_at in /new and /clear"
```

---

### Task 9: Run all tests

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```
Expected: All PASS

**Step 2: Fix any failures**

If any tests fail, fix them before proceeding.

**Step 3: Commit fixes if any**

---

### Task 10: Update bug report and move to fixed

**Files:**
- Modify: `docs/bugs/2025-12-29-session-binding-race-condition.md`

**Step 1: Update status**

Change `Status: Open` to `Status: Fixed` and add resolution after Summary:

```markdown
## Resolution

**Fixed by:** [session-binding-race-fix](../designs/2025-12-29-session-binding-race-fix.md)

**Fix summary:**
- Added `start_requested_at` timestamp to ThreadInfo (persisted)
- Added `get_session_creation_time()` to read first entry timestamp from jsonl
- `find_session_by_user_message()` now accepts `created_after` filter
- Both binding paths (`poll_for_session_thread` and `_bind_awaiting_threads`) now filter by creation time
- Only sessions created AFTER /start are considered

**Commits:** (add after implementation)
```

**Step 2: Move to fixed folder**

```bash
mkdir -p docs/bugs/fixed
mv docs/bugs/2025-12-29-session-binding-race-condition.md docs/bugs/fixed/
```

**Step 3: Commit**

```bash
git add docs/bugs/
git commit -m "docs: mark session binding race condition as fixed"
```

---

### Task 11: Manual testing

**Step 1: Restart bot**

```bash
./restart.sh
```

**Step 2: Test race condition scenario**

1. Have Thread A running with active Claude session
2. Press /start in new Thread B
3. Send SAME message text to Thread B that exists in Thread A
4. Verify Thread B waits for its OWN session (doesn't steal Thread A's)

**Step 3: Verify in config**

```bash
cat .config.json | jq '.projects.codogram.threads'
```

Check that each thread has unique session_id.

**Step 4: Test /new command**

1. In existing thread, run /new
2. Verify new session is bound correctly
3. Verify old session is not reused

**Step 5: Test bot restart during binding**

1. Press /start in new thread
2. Immediately restart bot: `./restart.sh`
3. Verify `start_requested_at` is preserved in config
4. Send message — should bind to correct session

---

## Known Limitations

### Multiple threads awaiting simultaneously

If two threads are both awaiting new sessions (`awaiting_new_session=True`) and a new session appears, BOTH may bind to the same session because `find_session_for_project()` returns only the latest session.

**Scenario:**
```
Thread A: /start at 10:00, awaiting, start_requested_at=10:00
Thread B: /start at 10:05, awaiting, start_requested_at=10:05
Session X: created at 10:01 (for Thread A)
Session Y: created at 10:06 (for Thread B)

Cycle 1: find_session_for_project → Y (latest)
         Thread A: 10:06 > 10:00 → bind A to Y ❌
Cycle 2: Thread B: 10:06 > 10:05 → bind B to Y ❌

Result: Both bound to Y, Session X orphaned.
```

**This is a separate bug**, not addressed by this plan. The current plan fixes the race condition where a thread binds to an OLD session (created BEFORE /start).

**Workaround:** Avoid running /start in multiple threads simultaneously.

**Future fix:** Use unique binding tokens or track expected session per thread.
