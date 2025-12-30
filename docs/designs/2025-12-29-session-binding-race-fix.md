# Session Binding Race Condition Fix

**Date:** 2025-12-29
**Status:** Proposed
**Bug:** [session-binding-race-condition](../bugs/2025-12-29-session-binding-race-condition.md)

## Problem

When user presses `/start` in a new topic while Claude is actively running in another topic, the new thread can incorrectly bind to the existing thread's session.

**Root cause:** `find_session_by_user_message` searches by message text. If:
1. New session hasn't been created yet (Claude initializing)
2. Or message text matches another thread's last message

...the wrong session gets bound.

## Decision

**Use session creation time filtering (Option 3 from bug report).**

Record the time when `/start` was requested. Only consider sessions created AFTER that time.

### Why this approach

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| 1. Verify tmux match | Direct correlation | No tmux info in jsonl, complex | ❌ |
| 2. Binding token | Reliable, unique | Visible in history, complex | Overkill |
| **3. Creation time** | Simple, sufficient | Needs timestamp storage | ✅ |
| 4. Wait longer | Easy | Unreliable, bad UX | ❌ |

**Option 3** provides the best balance of simplicity and reliability.

## Design

### New field: `start_requested_at`

```python
@dataclass
class ThreadInfo:
    name: str
    session_id: str | None = None
    jsonl_path: Path | None = None
    awaiting_new_session: bool = False
    last_sent_message: str | None = None
    start_requested_at: float | None = None  # NEW: time.time() when /start was pressed
```

### Flow

```
1. User presses /start in Thread B
2. Record thread.start_requested_at = time.time()
3. Launch Claude in tmux
4. poll_for_session_thread starts searching
5. For each session jsonl:
   - Get session creation time from first entry timestamp
   - If created_at < start_requested_at → skip (too old)
   - If message matches → bind!
6. On successful bind: clear start_requested_at = None
```

### Key function: `get_session_creation_time`

```python
def get_session_creation_time(jsonl_path: Path) -> float:
    """Get timestamp of first entry in session jsonl.

    This is more reliable than st_mtime/st_ctime because:
    - st_mtime updates on every write
    - st_ctime is inode change time, not creation time (Linux)
    - First entry timestamp IS the session creation time
    """
    with open(jsonl_path) as f:
        first_line = f.readline()
        if first_line:
            entry = json.loads(first_line)
            return entry.get("timestamp", 0)
    return 0
```

### Modified: `find_session_by_user_message`

```python
def find_session_by_user_message(
    project_dir: str,
    user_message: str,
    exclude_session_ids: list[str] | None = None,
    created_after: float | None = None,  # NEW parameter
) -> tuple[str, Path] | None:

    for jsonl_path in jsonl_files:
        # NEW: Filter by creation time
        if created_after is not None:
            session_created = get_session_creation_time(jsonl_path)
            if session_created < created_after:
                continue  # Session created before /start — skip

        # Existing logic
        last_msg = get_last_user_message_from_jsonl(jsonl_path)
        if last_msg == user_message:
            return (session_id, jsonl_path)
```

### Modified: `poll_for_session_thread`

```python
async def poll_for_session_thread(...):
    # Pass start_requested_at to filter old sessions
    result = find_session_by_user_message(
        project_dir=project.cwd,
        user_message=thread.last_sent_message,
        exclude_session_ids=existing_session_ids,
        created_after=thread.start_requested_at,  # NEW
    )

    if result:
        # Clear after successful bind
        thread.start_requested_at = None
        project_manager._save()
```

### Modified: `/start` command

```python
async def _launch_claude_in_thread(...):
    thread.start_requested_at = time.time()  # NEW: Record /start time
    project_manager._save()
    # ... existing launch logic
```

## Edge Cases

### Case 1: Same message in both threads

```
Thread A: "Hello" at 10:00, session A created 10:01
Thread B: /start at 10:05, "Hello" at 10:06

Search: session A created 10:01 < 10:05 → SKIP
        session B created 10:07 > 10:05 → CHECK message → BIND ✓
```

### Case 2: New session not created yet

```
Thread A: "Hello" at 10:00
Thread B: /start at 10:05, "Hello" at 10:06
(Session B not created yet)

Search: session A created 10:01 < 10:05 → SKIP
        nothing found → continue polling
        ...
        session B appears 10:07 > 10:05 → BIND ✓
```

### Case 3: /start in old thread

```
Thread created long ago, /start pressed now

start_requested_at = now
Only sessions created after now are considered → correct behavior
```

## Persistence

`start_requested_at` must be persisted to survive bot restarts:

```python
# In _save():
"start_requested_at": thread.start_requested_at

# In _load_projects():
thread.start_requested_at = thread_data.get("start_requested_at")
```

## Future Enhancement

If this solution proves insufficient (unforeseen edge case), add **binding token** as reinforcement:

```python
# On /start:
thread.binding_token = str(uuid4())[:8]
tmux.send_keys(f"# codogram:bind:{thread.binding_token}")

# In search: also match by token presence
```

But for now, time-based filtering should be sufficient.

## Files to Modify

1. `src/codogram/session_manager.py` — add `start_requested_at` field, persistence
2. `src/codogram/history_reader.py` — add `get_session_creation_time`, modify `find_session_by_user_message`
3. `src/codogram/history_watcher.py` — pass `created_after` to search, clear after bind
4. `src/codogram/bot.py` — set `start_requested_at` in `/start`
