# Bug: Session binding race condition during /start

**Date:** 2025-12-29
**Severity:** High
**Status:** Fixed

## Resolution

**Fixed by:** [session-binding-race-fix](../designs/2025-12-29-session-binding-race-fix.md)

**Fix summary:**
- Added `start_requested_at` timestamp to ThreadInfo (persisted)
- Added `get_session_creation_time()` to read first entry timestamp from jsonl
- `find_session_by_user_message()` now accepts `created_after` filter
- Both binding paths (`poll_for_session_thread` and `_bind_awaiting_threads`) now filter by creation time
- Only sessions created AFTER /start are considered

**Commits:**
- `6f9ab3f` feat(history): add get_session_creation_time function
- `e7f2099` feat(session): add start_requested_at field with persistence
- `bf83fe9` feat(history): add created_after filter to find_session_by_user_message
- `23b9c65` fix(watcher): filter by created_after in poll_for_session_thread
- `3d71643` fix(watcher): filter by created_after in _bind_awaiting_threads
- `7803247` fix(watcher): clear start_requested_at in _bind_thread_to_session
- `1847384` feat(launch_animation): set start_requested_at when launching Claude
- `ce66532` feat(bot): set start_requested_at in /new and /clear

## Summary

When a user does `/start` in a new topic while Claude is actively running in another topic, the new thread can incorrectly bind to the existing thread's session. This causes messages from one Claude session to appear in multiple Telegram threads.

## Reproduction steps

1. Have project with Thread A (e.g., "rate-limit") actively running Claude session A
2. Press `/start` in new topic → creates Thread B (e.g., "modularization")
3. Send a message in Thread B
4. **Bug:** Thread B binds to session A (Thread A's session)
5. Messages from session A now appear in BOTH Thread A and Thread B

## Evidence from config

```
1256 (sublime): session=405fe3e1
1038 (immortal): session=405fe3e1
```

Two different threads bound to the same session.

## Root cause

The session binding logic in `find_session_by_user_message` (history_reader.py:152-178) has a race condition:

```python
for jsonl_path in jsonl_files:
    last_msg = get_last_user_message_from_jsonl(jsonl_path)
    if last_msg == user_message:  # Matches by MESSAGE TEXT
        session_id = jsonl_path.stem
        return (session_id, jsonl_path)
```

**Problem:** If the user sends the same message text to both threads, OR if the new session's jsonl hasn't been created yet when the search happens, the search will match the wrong session.

### Timeline of the bug

```
T=0: Thread A running, session A, last user message = "Hello"
T=1: User does /start in new topic → Thread B created
T=2: Claude launches in Thread B's tmux
T=3: User sends "Hello" to Thread B
T=4: Message sent to Thread B's tmux
T=5: poll_for_session_thread starts searching for session with "Hello"
T=6: Session B's jsonl either:
     - Not created yet (Claude still initializing)
     - Created but not yet written the message
T=7: find_session_by_user_message finds session A (has "Hello")
T=8: Thread B bound to session A (WRONG!)
```

## Affected code

- `src/codogram/history_reader.py:152-178` - `find_session_by_user_message`
- `src/codogram/history_watcher.py:244-300` - `poll_for_session_thread`

## Possible fixes

### Option 1: Verify tmux session matches

Before binding, verify that the session's jsonl shows activity from the expected tmux session. This requires additional correlation data.

### Option 2: Use unique binding token

Generate a unique token for each thread at /start time. Send this token as the first message. Only bind if the session contains this exact token.

```python
# On /start:
thread.binding_token = str(uuid4())[:8]
tmux.send_keys(f"# BIND:{thread.binding_token}")

# In find_session:
if f"# BIND:{thread.binding_token}" in session_content:
    return session
```

### Option 3: Check session creation time

Only match sessions created AFTER the thread was created:

```python
if session_jsonl.stat().st_ctime < thread.created_at:
    continue  # Skip sessions created before this thread
```

### Option 4: Wait longer before searching

Add delay before searching to ensure new session has time to be created:

```python
await asyncio.sleep(5)  # Wait for Claude to create session file
result = find_session_by_user_message(...)
```

## Workaround

Run `/start` in the affected topic again to rebind to correct session.

## Related

- Fixed bug: [Thread session mixup](fixed/2025-12-29-thread-session-mixup.md) - similar but different trigger (during message, not /start)
