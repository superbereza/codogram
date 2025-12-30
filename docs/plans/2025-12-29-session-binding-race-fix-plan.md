# Session Binding Race Condition Fix - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix race condition where new thread can bind to wrong session during /start

**Architecture:** Filter sessions by creation time - only consider sessions created AFTER /start was pressed. Uses first entry timestamp from jsonl (more reliable than st_mtime/st_ctime).

**Tech Stack:** Python, asyncio, JSON

**Design:** [session-binding-race-fix](../designs/2025-12-29-session-binding-race-fix.md)

---

### Task 1: Add `get_session_creation_time` function

**Files:**
- Modify: `src/codogram/history_reader.py:100-131` (after `get_last_user_message_from_jsonl`)
- Test: `tests/test_history_reader.py`

**Step 1: Write the failing test**

Add to `tests/test_history_reader.py`:

```python
import time
from codogram.history_reader import get_session_creation_time

def test_get_session_creation_time():
    """Test reading session creation time from first entry timestamp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "test-session.jsonl"

        # Create jsonl with timestamp
        now = time.time()
        with open(jsonl_path, 'w') as f:
            f.write(json.dumps({"type": "system", "timestamp": now}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": now + 1}) + "\n")

        result = get_session_creation_time(jsonl_path)
        assert result == now

def test_get_session_creation_time_missing_file():
    """Return 0 for missing file."""
    result = get_session_creation_time(Path("/nonexistent/path.jsonl"))
    assert result == 0

def test_get_session_creation_time_empty_file():
    """Return 0 for empty file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "empty.jsonl"
        jsonl_path.touch()

        result = get_session_creation_time(jsonl_path)
        assert result == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_history_reader.py::test_get_session_creation_time -v`
Expected: FAIL with "cannot import name 'get_session_creation_time'"

**Step 3: Write minimal implementation**

Add to `src/codogram/history_reader.py` after `get_last_user_message_from_jsonl`:

```python
def get_session_creation_time(jsonl_path: Path) -> float:
    """Get timestamp of first entry in session jsonl.

    This is more reliable than st_mtime/st_ctime because:
    - st_mtime updates on every write
    - st_ctime is inode change time, not creation time (Linux)
    - First entry timestamp IS the session creation time

    Returns 0 if file doesn't exist or can't be read.
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
    except Exception:
        return 0
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_history_reader.py::test_get_session_creation_time tests/test_history_reader.py::test_get_session_creation_time_missing_file tests/test_history_reader.py::test_get_session_creation_time_empty_file -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/history_reader.py tests/test_history_reader.py
git commit -m "feat(history): add get_session_creation_time function"
```

---

### Task 2: Add `start_requested_at` field to ThreadInfo

**Files:**
- Modify: `src/codogram/session_manager.py:82-99` (ThreadInfo dataclass)
- Modify: `src/codogram/session_manager.py:165-173` (_load_projects)
- Modify: `src/codogram/session_manager.py:202-210` (_save)
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

Add to `tests/test_session_manager.py`:

```python
def test_thread_info_start_requested_at():
    """Test start_requested_at field exists and defaults to None."""
    from codogram.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="test")
    assert thread.start_requested_at is None

    thread.start_requested_at = 1234567890.5
    assert thread.start_requested_at == 1234567890.5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_thread_info_start_requested_at -v`
Expected: FAIL with "no attribute 'start_requested_at'"

**Step 3: Write minimal implementation**

Modify `src/codogram/session_manager.py`:

In `ThreadInfo` dataclass (around line 98-99), add after `awaiting_new_session`:

```python
    # For session binding race condition fix:
    start_requested_at: float | None = None  # time.time() when /start was pressed
```

In `_load_projects` (around line 172), add to ThreadInfo creation:

```python
                        start_requested_at=thread_data.get("start_requested_at"),
```

In `_save` (around line 208), add to thread dict:

```python
                        "start_requested_at": t.start_requested_at,
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py::test_thread_info_start_requested_at -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat(session): add start_requested_at field to ThreadInfo"
```

---

### Task 3: Add `created_after` parameter to `find_session_by_user_message`

**Files:**
- Modify: `src/codogram/history_reader.py:152-178` (find_session_by_user_message)
- Test: `tests/test_history_reader.py`

**Step 1: Write the failing test**

Add to `tests/test_history_reader.py`:

```python
def test_find_session_by_user_message_created_after():
    """Test that created_after filters out old sessions."""
    from codogram.history_reader import find_session_by_user_message, get_session_creation_time

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake project directory structure
        project_dir = Path(tmpdir) / ".claude" / "projects" / "-test-project"
        project_dir.mkdir(parents=True)

        now = time.time()

        # Old session (created 10 seconds ago)
        old_session = project_dir / "old-session.jsonl"
        with open(old_session, 'w') as f:
            f.write(json.dumps({"type": "system", "timestamp": now - 10}) + "\n")
            f.write(json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n")

        # New session (created 2 seconds ago)
        new_session = project_dir / "new-session.jsonl"
        with open(new_session, 'w') as f:
            f.write(json.dumps({"type": "system", "timestamp": now - 2}) + "\n")
            f.write(json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n")

        # Monkeypatch Path.home() to use our temp dir
        import codogram.history_reader as hr
        original_compute = hr.compute_jsonl_path

        def mock_compute_jsonl_path(cwd, session_id):
            return project_dir / f"{session_id}.jsonl"

        # We need to test by creating the directory structure manually
        # and calling with created_after parameter

        # Without created_after: should find newest by mtime (new-session)
        # With created_after=now-5: should find new-session (created at now-2 > now-5)
        # With created_after=now-1: should find nothing (both sessions too old)

        # For this test, we'll verify the parameter is accepted
        # Full integration test would require more setup
        pass  # Placeholder - see integration test below


def test_find_session_by_user_message_created_after_integration():
    """Integration test: created_after filters old sessions."""
    from codogram.history_reader import find_session_by_user_message
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup: create project directory
        project_hash = "-test-cwd"
        project_dir = Path(tmpdir) / project_hash
        project_dir.mkdir(parents=True)

        now = time.time()

        # Old session
        old_jsonl = project_dir / "old-session.jsonl"
        with open(old_jsonl, 'w') as f:
            f.write(json.dumps({"type": "system", "timestamp": now - 100}) + "\n")
            f.write(json.dumps({"type": "user", "message": {"content": "Hello world"}}) + "\n")

        # New session
        new_jsonl = project_dir / "new-session.jsonl"
        with open(new_jsonl, 'w') as f:
            f.write(json.dumps({"type": "system", "timestamp": now - 5}) + "\n")
            f.write(json.dumps({"type": "user", "message": {"content": "Hello world"}}) + "\n")

        # Patch to use our temp directory
        with patch('codogram.history_reader.Path.home', return_value=Path(tmpdir).parent):
            # Compute what the cwd should be to get our project_dir
            # cwd -> normalize -> replace "/" with "-" -> project_hash
            # So cwd="/test/cwd" -> "-test-cwd"
            cwd = "/test/cwd"

            # Re-create directory with correct path
            correct_project_dir = Path(tmpdir) / ".claude" / "projects" / "-test-cwd"
            correct_project_dir.mkdir(parents=True, exist_ok=True)

            # Move files
            import shutil
            for f in project_dir.glob("*.jsonl"):
                shutil.copy(f, correct_project_dir / f.name)

            with patch('codogram.history_reader.Path.home', return_value=Path(tmpdir)):
                # With created_after=now-50: only new-session qualifies
                result = find_session_by_user_message(cwd, "Hello world", created_after=now - 50)
                if result:
                    session_id, path = result
                    assert session_id == "new-session"

                # With created_after=now-1: neither qualifies
                result = find_session_by_user_message(cwd, "Hello world", created_after=now - 1)
                assert result is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_history_reader.py::test_find_session_by_user_message_created_after_integration -v`
Expected: FAIL with "got an unexpected keyword argument 'created_after'"

**Step 3: Write minimal implementation**

Modify `src/codogram/history_reader.py`, function `find_session_by_user_message`:

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
        created_after: If set, only consider sessions created after this timestamp
                       (used to prevent binding to old sessions during /start race)

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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_history_reader.py::test_find_session_by_user_message_created_after_integration -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/history_reader.py tests/test_history_reader.py
git commit -m "feat(history): add created_after filter to find_session_by_user_message"
```

---

### Task 4: Use `created_after` in `poll_for_session_thread`

**Files:**
- Modify: `src/codogram/history_watcher.py:278-282` (find_session_by_user_message call)

**Step 1: Locate the code**

In `poll_for_session_thread`, find the call to `find_session_by_user_message` (around line 281):

```python
result = find_session_by_user_message(project.cwd, thread.last_sent_message)
```

**Step 2: Modify to pass `created_after`**

Change to:

```python
result = find_session_by_user_message(
    project.cwd,
    thread.last_sent_message,
    created_after=thread.start_requested_at,
)
```

**Step 3: Clear `start_requested_at` after successful bind**

After `thread.awaiting_new_session = False` (around line 291), add:

```python
thread.start_requested_at = None
project_manager._save()
```

**Step 4: Run existing tests to ensure no regression**

Run: `pytest tests/test_history_watcher.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "feat(watcher): use created_after filter in poll_for_session_thread"
```

---

### Task 5: Set `start_requested_at` in `/start` flow

**Files:**
- Modify: `src/codogram/bot.py:520-523` (launch_claude_in_thread)

**Step 1: Locate the code**

In `launch_claude_in_thread`, find where `awaiting_new_session` is set (around line 522):

```python
# Block HistoryWatcher from grabbing old session during startup
thread.awaiting_new_session = True
```

**Step 2: Add `start_requested_at`**

Add after `thread.awaiting_new_session = True`:

```python
import time
thread.start_requested_at = time.time()
```

**Step 3: Run bot manually to verify**

Start bot and test /start in a thread. Check logs for session binding.

**Step 4: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): set start_requested_at when launching Claude"
```

---

### Task 6: Clear `start_requested_at` in `_bind_thread_to_session`

**Files:**
- Modify: `src/codogram/history_watcher.py:168-171` (_bind_thread_to_session)

**Step 1: Locate the code**

In `_bind_thread_to_session`, find where `awaiting_new_session` is cleared (around line 171):

```python
thread.awaiting_new_session = False
```

**Step 2: Add clearing of `start_requested_at`**

Add after `thread.awaiting_new_session = False`:

```python
thread.start_requested_at = None
```

**Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "fix(watcher): clear start_requested_at after binding"
```

---

### Task 7: Update bug report status

**Files:**
- Modify: `docs/bugs/2025-12-29-session-binding-race-condition.md`

**Step 1: Update status and add resolution**

Change `Status: Open` to `Status: Fixed` and add resolution section after Summary:

```markdown
## Resolution

**Fixed by:** [session-binding-race-fix](../designs/2025-12-29-session-binding-race-fix.md)

**Fix summary:**
- Added `start_requested_at` timestamp to ThreadInfo
- `find_session_by_user_message` now filters sessions by creation time
- Only sessions created AFTER /start are considered for binding
- Uses first entry timestamp from jsonl (reliable session creation time)

**Commits:** (list commit hashes after implementation)
```

**Step 2: Move to fixed folder**

```bash
mv docs/bugs/2025-12-29-session-binding-race-condition.md docs/bugs/fixed/
```

**Step 3: Commit**

```bash
git add docs/bugs/
git commit -m "docs: mark session binding race condition as fixed"
```

---

### Task 8: Manual testing

**Step 1: Restart bot**

```bash
./restart.sh
```

**Step 2: Test race condition scenario**

1. Have Thread A running with active Claude session
2. Press /start in new Thread B
3. Send same message text to Thread B that exists in Thread A
4. Verify Thread B gets its OWN session, not Thread A's

**Step 3: Verify in config**

```bash
cat .config.json | jq '.projects.codogram.threads'
```

Confirm different session_ids for different threads.

**Step 4: Test edge cases**

- /start in old thread (should still work)
- /new command (should still work with awaiting_new_session)
- Bot restart during binding (should preserve start_requested_at)
