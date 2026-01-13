# Stale Worktree Recovery

**Date:** 2026-01-12
**Status:** Draft

## Problem

When a worktree is deleted externally (e.g., after merging a branch), but the Telegram topic still exists, commands crash because they try to access a non-existent directory.

**Affected commands:** `/resume`, `/start`, `/finish`, `/branch`

## Solution

Detect stale `worktree_path` and offer recovery options instead of crashing.

## Detection

Before any operation that uses `worktree_path`:

```python
if thread.worktree_path and not Path(thread.worktree_path).exists():
    # stale worktree detected
```

Also check if the branch still exists:

```python
branch_exists = branch_exists(project.cwd, thread.name)
```

## Scenarios

### 1. `/resume` or `/start` — Worktree missing, branch exists

```
`[!]` Worktree not found: `.worktrees/my-feature`

Branch `my-feature` exists.

• Recreate worktree — recreate folder and resume session
• Resume in main — archive topic, continue in main
• Cancel
```

Buttons: `[Recreate worktree]` `[Resume in main]` `[Cancel]`

**Actions:**
- **Recreate worktree:** `git worktree add .worktrees/{name} {name}`, then start Claude
- **Resume in main:** archive topic, show success message
- **Cancel:** do nothing

### 2. `/resume` or `/start` — Worktree missing, branch missing

```
`[!]` Worktree not found: `.worktrees/my-feature`

Branch `my-feature` not found (merged?).

• Create new — create branch + worktree, resume session
• Resume in main — archive topic, continue in main
• Cancel
```

Buttons: `[Create new]` `[Resume in main]` `[Cancel]`

**Actions:**
- **Create new:** create branch from main, create worktree, start Claude
- **Resume in main:** archive topic, show success message
- **Cancel:** do nothing

### 3. `/finish` — Worktree missing

Show warning, skip git operations, archive topic:

```
`[!]` Worktree not found: `.worktrees/my-feature`

Archiving topic without git cleanup.
```

Then proceed with normal archive flow.

### 4. `/branch` — Called from topic with stale worktree

Fallback to main as base branch with warning:

```
`[!]` Worktree not found, using main as base

Branch name?

Send name or pick random
```

Buttons: `[🔮 Magic name]` `[<<] Go back`

Then normal `/branch` flow using main as base.

### 5. Recreate fails

If worktree recreation fails, show error with manual options:

```
`[x]` Failed to recreate worktree: {detailed error}

What to do:
• /finish — archive this topic
• /thread — create new topic in main
• /branch — create new worktree branch
```

No buttons — user decides next action.

### 6. "Resume in main" chosen

Archive the topic and show confirmation:

```
`[v]` Topic archived

Use General or /thread for new session.
```

**Why archive?**
- Topic is named after the feature (e.g., "my-feature")
- Feature work is done (worktree deleted, branch merged)
- Continuing main work in "my-feature" topic is confusing

## Summary Table

| Situation | Command | Behavior |
|-----------|---------|----------|
| Worktree missing, branch exists | `/resume`, `/start` | Ask: Recreate / Resume in main / Cancel |
| Worktree missing, branch missing | `/resume`, `/start` | Ask: Create new / Resume in main / Cancel |
| Worktree missing | `/finish` | Warning + archive |
| Worktree missing | `/branch` | Warning + fallback to main as base |
| Recreate failed | any | Error + text with options (/finish, /thread, /branch) |
| "Resume in main" chosen | any | Archive topic + confirmation |

## Implementation Notes

### Files to modify

- `src/codogram/handlers/start.py` — `/start` in topic with stale worktree
- `src/codogram/handlers/sessions.py` — `/resume` recovery flow
- `src/codogram/handlers/finish.py` — skip git ops if worktree missing
- `src/codogram/handlers/branches.py` — fallback to main if stale worktree
- `src/codogram/services/` — new service for worktree recovery logic

### New helper functions

```python
def is_worktree_stale(thread: ThreadInfo) -> bool:
    """Check if thread has worktree_path that doesn't exist."""
    return bool(thread.worktree_path and not Path(thread.worktree_path).exists())

def get_worktree_state(thread: ThreadInfo, project_cwd: Path) -> WorktreeState:
    """Return state: OK, MISSING_WITH_BRANCH, MISSING_NO_BRANCH, or NO_WORKTREE."""
    ...
```

### Callback data format

```
wr_recreate:{thread_id}     — recreate worktree
wr_create:{thread_id}       — create new branch + worktree
wr_main:{thread_id}         — resume in main (archive topic)
wr_cancel:{thread_id}       — cancel
```
