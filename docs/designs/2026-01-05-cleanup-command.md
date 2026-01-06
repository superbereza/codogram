# /cleanup Command Design

## Overview

Explicit deletion of archived branches when disk space or git cleanup needed.

**Prerequisite:** Implement menu-redesign and session-resume first.

## Command

```
/cleanup [branch_name]
```

## Usage

### List all archived

```
/cleanup
```

Response:
```
`[i]` Archived branches:

• `feature-x` — 45 days inactive
• `bugfix-y` — 32 days inactive
• `experiment` — 12 days inactive

[Delete old (>30d)]  [Delete all]  [Cancel]
```

**Note:** "days inactive" = days since last jsonl modification (last Claude activity).

```python
def get_days_inactive(thread: ThreadInfo) -> int:
    """Get days since last Claude activity."""
    if not thread.jsonl_path:
        return 0
    jsonl = Path(thread.jsonl_path)
    if not jsonl.exists():
        return 0
    mtime = jsonl.stat().st_mtime
    return int((time.time() - mtime) / 86400)
```

### Delete specific

```
/cleanup feature-x
```

Response:
```
Delete `feature-x`?
- Worktree: .worktrees/feature-x/
- Git branch: feature-x

[Delete] [Cancel]
```

## What Gets Deleted

| Item | Deleted? | Why |
|------|----------|-----|
| Worktree directory | ✓ Yes | Free disk space |
| Git branch | ✓ Yes | Clean git state |
| Session jsonl | ✗ No | Preserve history |
| ThreadInfo | ✗ No | Mark `deleted: true` |

## ThreadInfo Field

```python
deleted: bool = False  # True after /cleanup
```

Threads with `deleted: true`:
- Hidden from `/help` thread lists
- Kept in config for history
- jsonl_path still valid (can read old sessions)

## Flow

```
/cleanup
    │
    ├── no args → list archived branches
    │   ├── [Delete old (>30d)] → confirm, delete where days_inactive > 30
    │   └── [Delete all] → confirm, delete all archived
    │
    └── with branch_name
        ├── branch exists + archived → check unmerged, confirm deletion
        ├── branch exists + not archived → "[!] Branch is active"
        └── branch not found → "[!] Branch not found"
```

## Implementation

### New file: `handlers/cleanup.py`

```python
@router.message(Command("cleanup"))
async def cleanup_command(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) == 1:
        # List archived branches
        await show_archived_list(message)
    else:
        # Delete specific branch
        branch_name = args[1]
        await confirm_delete_branch(message, branch_name)

def check_unmerged_commits(project_cwd: str, branch_name: str, base_branch: str) -> list[str]:
    """Check if branch has commits not in base branch."""
    result = subprocess.run(
        ["git", "log", f"{base_branch}..{branch_name}", "--oneline"],
        cwd=project_cwd, capture_output=True, text=True
    )
    if result.stdout.strip():
        return result.stdout.strip().split("\n")
    return []

def validate_worktree_path(worktree_path: str, project_cwd: str) -> bool:
    """Safety check: ensure path is within project and is a worktree."""
    path = Path(worktree_path).resolve()
    project = Path(project_cwd).resolve()

    # Must be child of project
    if not str(path).startswith(str(project)):
        return False

    # Must contain .worktrees segment
    if ".worktrees" not in str(path):
        return False

    return True

async def do_cleanup(thread: ThreadInfo, project: ProjectState):
    """Actually delete worktree and branch."""

    # 0. Kill tmux if running
    tmux_name = thread.get_tmux_session(project.project_name)
    if is_tmux_session_exists(tmux_name):
        kill_tmux_session(tmux_name)

    # 1. Validate and delete worktree directory
    if thread.worktree_path:
        if not validate_worktree_path(thread.worktree_path, project.cwd):
            raise ValueError(f"Invalid worktree path: {thread.worktree_path}")
        shutil.rmtree(thread.worktree_path, ignore_errors=True)

    # 2. Delete git branch (thread.name is the branch name)
    subprocess.run(
        ["git", "branch", "-D", thread.name],
        cwd=project.cwd,
        capture_output=True
    )

    # 3. Mark as deleted (keep ThreadInfo)
    thread.deleted = True
    thread.worktree_path = None  # Clear path since deleted

    # 4. Save config
    project_manager._save()
```

### Callback handlers

```python
@router.callback_query(F.data.startswith("cleanup:"))
async def cleanup_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]

    if action == "delete_old":
        # Show confirmation with count
        old_threads = [t for t in get_archived_threads() if get_days_inactive(t) > 30]
        await show_delete_old_confirmation(callback, len(old_threads))
    elif action == "confirm_old":
        # Delete all >30 days inactive
        for thread in get_archived_threads():
            if get_days_inactive(thread) > 30:
                await do_cleanup(thread, project)
    elif action == "delete_all":
        await show_delete_all_confirmation(callback)
    elif action == "confirm_all":
        for thread in get_archived_threads():
            await do_cleanup(thread, project)
    elif action.startswith("delete_"):
        thread_id = parts[2]
        unmerged = check_unmerged_commits(...)
        if unmerged:
            await show_unmerged_warning(callback, unmerged)
        else:
            await do_cleanup(thread, project)
    elif action == "cancel":
        await callback.message.delete()
```

## Messages

### Success
```
`[v]` Deleted: feature-x
```

### No archived branches
```
`[i]` No archived branches to clean up
```

### Branch is active
```
`[!]` Branch `feature-x` is active

Use /finish first to archive it.
```

### Unmerged commits warning
```
`[!]` Branch has unmerged commits:

• abc1234 Add feature X
• def5678 Fix bug Y

[Delete anyway] [Cancel]
```

### Delete old confirmation
```
`[!]` Delete 2 branches inactive >30 days?

• feature-x (45 days)
• bugfix-y (32 days)

[Yes, delete old] [Cancel]
```

### Delete all confirmation
```
`[!]` Delete ALL 3 archived branches?

This cannot be undone.

[Yes, delete all] [Cancel]
```

## Edge Cases

| Situation | Handling |
|-----------|----------|
| Worktree already deleted manually | Skip, just delete branch |
| Git branch already deleted | Skip, just mark deleted |
| Branch not found in config | Error message |
| Delete while tmux running | Kill tmux first, then delete |
| Unmerged commits exist | Show warning, require confirmation |
| Invalid worktree path | Raise error, don't delete |
