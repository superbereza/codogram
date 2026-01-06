# Session Resume Design

## Overview

Add ability to resume previous Claude session when starting a thread that has `session_id` stored.

## Key Decision: Keep Worktrees

Worktrees are **not deleted** after branch merge/archive. This gives us:
- Resume always works (worktree always exists)
- Simple architecture (no cd hacks)
- Natural lifecycle (session lives with worktree)
- Cleanup is explicit operation when needed

## Architecture

### Threads (no worktree)
- Launch Claude in `project.cwd`
- Session stored in `~/.claude/projects/-{normalized-cwd}/`
- Resume: `claude --resume {session_id}`

Example:
```
cwd:     /home/user/project
jsonl:   ~/.claude/projects/-home-user-project/{session_id}.jsonl
```

### Branches (with worktree)
- Launch Claude in `worktree_path` (e.g. `.worktrees/feature-x/`)
- Session stored in `~/.claude/projects/-{normalized-worktree}/`
- Resume: `claude --resume {session_id}`
- Worktree persists → session persists

Example:
```
worktree: /home/user/project/.worktrees/feature-x
jsonl:    ~/.claude/projects/-home-user-project-.worktrees-feature-x/{session_id}.jsonl
```

## Flow

```
/start in thread
    │
    ├── tmux session running?
    │   ├── YES + Claude ready → "[v] Already running: tmux attach -t ..."
    │   └── YES + Claude not ready → kill tmux, continue below
    │
    ├── has worktree_path? (branch)
    │   ├── worktree exists?
    │   │   ├── YES + has session_id + jsonl exists → resume in worktree
    │   │   ├── YES + has session_id + no jsonl → "[!] Session not found" [Start new]
    │   │   ├── YES + no session_id → normal launch in worktree
    │   │   └── NO → "[!] Worktree not found" [Recreate] [Cancel]
    │   │
    └── no worktree (thread)
        ├── has session_id + jsonl exists → resume
        ├── has session_id + no jsonl → "[!] Session not found" [Start new]
        └── no session_id → normal launch
```

**Important:** Check tmux running FIRST before any launch/resume logic.

## Claude Commands

| Scenario | cwd | Command |
|----------|-----|---------|
| Thread, no session | project.cwd | `claude` |
| Thread, with session | project.cwd | `claude --resume {session_id}` |
| Branch, no session | worktree_path | `claude` |
| Branch, with session | worktree_path | `claude --resume {session_id}` |

## Worktree Path

Worktrees created inside `.worktrees/` directory:

```
/project/
├── .worktrees/
│   ├── feature-x/
│   ├── bugfix-y/
│   └── experiment-z/
├── src/
└── ...
```

Add to `.gitignore`:
```
.worktrees/
```

## Files to Modify

1. **launch_animation.py** - add `session_id` parameter for --resume
2. **services/branch.py** - change worktree path to `.worktrees/{branch}`
3. **services/branch.py** - remove worktree deletion on finish
4. **handlers/start.py** - check session_id and jsonl before launch
5. **handlers/callbacks.py** - retry/start_new handlers for errors

## Messages (per tone-of-voice.md)

### Resuming
```
`[~]` Resuming session...
```

### Success
```
`[v]` Session resumed

Attach: `tmux attach -t {name}`
```

### Session file missing
```
`[!]` Previous session not found
```
Buttons: `Start new` / `Cancel`

### Worktree missing
```
`[!]` Worktree not found: {path}
```
Buttons: `Recreate` / `Cancel`

## Callback Data Format

Button callbacks for error handling:

| Button | Callback Data |
|--------|---------------|
| Start new | `resume:start_new:{thread_id}` |
| Cancel | `resume:cancel:{thread_id}` |
| Recreate | `resume:recreate:{thread_id}` |
| Retry | `resume:retry:{thread_id}` |

Handler in `handlers/callbacks.py`:
```python
@router.callback_query(F.data.startswith("resume:"))
async def resume_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]  # start_new, cancel, recreate, retry
    thread_id = int(parts[2]) if parts[2] != "None" else None

    if action == "start_new":
        thread.session_id = None  # Clear stale session
        await launch_with_animation(...)
    elif action == "cancel":
        await callback.message.delete()
    elif action == "recreate":
        await recreate_worktree(...)
```

## Implementation

### Changes to launch_animation.py

```python
async def launch_with_animation(
    ...,
    session_id: str | None = None,  # NEW: for --resume
    cwd: str | None = None,         # NEW: override for branches
):
    # Use worktree cwd for branches
    actual_cwd = cwd or project.cwd
    tmux = TmuxSession(tmux_name, actual_cwd)

    # Build command
    cmd = "claude"
    if session_id:
        cmd = f"claude --resume {session_id}"

    # Update status message
    status = "`[~]` Resuming session..." if session_id else "`[~]` Starting Claude..."

    # Launch
    tmux.send(cmd)
```

### Changes to services/branch.py

```python
# Worktree path: inside .worktrees/
worktree_path = project_root / ".worktrees" / branch_name

# On branch_finish: DON'T delete worktree
# Just mark as archived in config
thread.archived = True
```

### Changes to start flow

```python
# Before launch, check resume conditions
if thread.session_id:
    jsonl_path = Path(thread.jsonl_path)
    if jsonl_path.exists():
        # Resume
        await launch_with_animation(..., session_id=thread.session_id)
    else:
        # Session file missing - show error with buttons
        await show_session_not_found_error(...)
else:
    # Normal launch
    await launch_with_animation(...)
```

## Cleanup Strategy

See separate design: `2026-01-05-cleanup-command.md`

## Branch Lifecycle

```
┌─────────┐   /branch    ┌────────┐   /start   ┌─────────┐
│ (none)  │ ──────────▶  │ active │ ─────────▶ │ running │
└─────────┘              └────────┘            └─────────┘
                              │                     │
                              │ /finish             │ /finish
                              ▼                     ▼
                         ┌──────────┐         ┌──────────┐
                         │ archived │ ◀────── │ archived │
                         └──────────┘         └──────────┘
                              │  ▲
                      /cleanup│  │/start (resume)
                              ▼  │
                         ┌─────────┐
                         │ deleted │
                         └─────────┘
```

| State | tmux | worktree | git branch | session | RAM |
|-------|------|----------|------------|---------|-----|
| active | - | ✓ | ✓ | - | 0 |
| running | ✓ | ✓ | ✓ | ✓ | ~500MB |
| archived | - | ✓ | ✓ | ✓ | **0** |
| deleted | - | - | - | ✓ (jsonl kept) | 0 |

## Edge Cases

1. **Session cleared in Claude** (`/clear`) - resume fails, offer start new
2. **Worktree deleted manually** - recreate from existing git branch
3. **Git branch deleted** - worktree still works (detached HEAD)
4. **Multiple sessions for same thread** - use latest session_id from config
5. **tmux exists but Claude not running** - kill tmux, start fresh

## Known Limitation

**User does `/new` or `/clear` directly in Claude (not through bot):**
- Bot doesn't detect this
- `session_id` in config stays old
- Resume will load old session context

**Workaround:** Use bot's `/clear` command, not Claude's directly.

This is accepted limitation — user should use bot commands for session management.
