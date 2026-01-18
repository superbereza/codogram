# Auto-resume on Message

## Overview

Auto-launch Claude when user sends message but tmux doesn't exist.

**Trigger conditions:**
- Project registered for chat_id
- Thread exists (not pending)
- Tmux session doesn't exist

**Behavior:**
1. Show: `` `[~]` Tmux session not found, launching... ``
2. Launch Claude:
   - If `thread.session_id` exists → `claude --resume {session_id}`
   - Otherwise → `claude`
3. Queue user message (text + files)
4. Send all queued messages after Claude ready

**Where NOT triggered:**
- `RouteAction.NO_PROJECT` - no project, silent
- `RouteAction.CREATE_PENDING` / `SKIP_PENDING` - unknown topic
- Tmux exists but Claude not ready - just send to tmux

## Implementation Architecture

### New RouteAction

```python
class RouteAction(Enum):
    ...
    AUTO_RESUME = "auto_resume"  # Tmux not found, can auto-launch
```

### Changes in MessageRouterService.route()

After checking `session_id is None` (START_BINDING), add tmux check:

```python
# Check if tmux exists
tmux_name = thread.get_tmux_session(project.project_name)
tmux = TmuxSession(tmux_name, cwd)
if not tmux.exists():
    return RouteResult(
        action=RouteAction.AUTO_RESUME,
        project=project,
        thread=thread,
        tmux_name=tmux_name,
        cwd=cwd,
    )
```

### Message Queue in ThreadInfo

```python
@dataclass
class ThreadInfo:
    ...
    pending_messages: list[dict] = field(default_factory=list)
    # dict format: {"text": str|None, "file_path": str|None}
    # Not persisted - lost on bot restart (acceptable)
```

### Handler in messages.py

```python
case RouteAction.AUTO_RESUME:
    await _handle_auto_resume(message, result, telegram_queue)
```

## Auto-resume Handler Flow

```
_handle_auto_resume(message, result, telegram_queue):
    1. Show notification: `[~]` Tmux session not found, launching...

    2. Save message to queue:
       - Text → {"text": ..., "file_path": None}
       - File → save to disk, {"text": caption, "file_path": ...}

    3. Check race condition:
       - If thread.launch_task already running → only add to queue, return

    4. Start launch_with_animation():
       - session_id = thread.session_id (may be None)
       - cwd = thread.worktree_path or project.cwd

    5. After launch (in callback or after await):
       - Send all pending_messages to tmux
       - Clear queue
```

**Race protection:** If user sends 3 messages in a row:
- 1st: starts launch, adds to queue
- 2nd, 3rd: see launch_task active, only add to queue
- After ready: all 3 are sent

## Strings

```python
AUTO_RESUME_LAUNCHING = f"{STATUS_PENDING} Tmux session not found, launching\\.\\.\\."
```

## Data Model

**PendingMessage format (dict, not dataclass):**
```python
{"text": str | None, "file_path": str | None}
```

**Not persisted** - if bot restarts during launch, messages are lost. Acceptable:
- Launch takes ~30 sec
- Probability of restart during this window is low
- Not worth complicating persistence

## Files to Modify

1. **`services/message_router.py`:**
   - Add `RouteAction.AUTO_RESUME`
   - In `route()`: check `tmux.exists()` before returning `SEND_TO_TMUX`

2. **`session_manager.py`:**
   - Add `pending_messages: list[dict]` to `ThreadInfo`
   - Don't persist (transient field)

3. **`handlers/messages.py`:**
   - Add `case RouteAction.AUTO_RESUME:`
   - Implement `_handle_auto_resume()`
   - After launch, send queue

4. **`strings.py`:**
   - Add `AUTO_RESUME_LAUNCHING`

5. **`launch_animation.py`:**
   - Add callback/hook to send pending messages after ready
   - Or return True/False and handle in handler
