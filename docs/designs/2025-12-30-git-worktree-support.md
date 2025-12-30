# Git Worktree Support Design

**Status:** Design
**Date:** 2025-12-30

## Problem

All topic sessions share the same directory (`/dev/project`) and git state (main branch). This causes:
- Changes in one session visible to others
- Conflicts between parallel sessions
- Impossible to work on multiple features simultaneously

## Solution

Each topic (except General) gets its own git worktree:

| Topic | Directory | Branch |
|-------|-----------|--------|
| General | `/dev/project` | main |
| auth | `/dev/project-auth` | auth |
| fix-bug | `/dev/project-fix-bug` | fix-bug |

## Commands

### `/branch_create [name]`

Creates worktree + branch + topic + tmux + Claude session.

**Flow:**

```
/branch_create [name]
    │
    ├─ Not a forum group?
    │  └─ `[!]` Topics required for /branch_create. Enable in group settings → Topics
    │
    ├─ No git repository?
    │  └─ `[x]` Git repository required for /branch_create
    │
    ├─ From General (main):
    │  └─ Uncommitted changes?
    │     ├─ No → create from main
    │     └─ Yes → popup:
    │        [Create clean (from last commit)]
    │        [Commit first]  → sends to Claude, replaces message with:
    │                         `[~]` Sent: "Commit current changes in logical chunks with descriptive messages."
    │
    │                         Run /branch_create again after commit.
    │        [<<] Go back, I'll Claude it
    │
    └─ From topic (branch feature-x):
       └─ Popup: "Create from:"
          [main]
          [feature-x]
          [<<] Go back, I'll Claude it
              │
              └─ If feature-x selected + uncommitted:
                 [Commit first]  → same behavior as above
                 [Create from last commit]
                 [<<] Go back, I'll Claude it
```

**Naming:**
- `name` provided → use as topic name, branch name, directory suffix
- `name` not provided → magic name (arcane, mystic, celestial...)

**Note:** `/branch_create` works independently of current Claude session. It creates everything from scratch (worktree, topic, tmux, Claude). No need to have Claude running first.

**Result:**
```
`[v]` Branch auth created

Worktree: /dev/project-auth
Attach: `tmux attach -t claude-project-auth`
```

### `/branch_finish`

Merges branch and cleans up worktree + tmux + topic.

**Flow:**

```
/branch_finish
    │
    ├─ Not a worktree topic?
    │  └─ `[!]` /branch_finish only works in worktree topics. Use /thread_close for this topic.
    │
    ├─ Worktree directory missing?
    │  └─ Cleanup remaining: tmux, branch, topic (skip worktree removal)
    │
    ├─ Uncommitted changes in current branch?
    │  └─ `[!]` Uncommitted changes. Commit or stash first.
    │
    └─ Popup: "Finish `auth` branch:"
       [Merge → main]
       [Merge → feature-x]  ← only if base_branch exists (check: git rev-parse --verify)
       [!!] Delete without merge
       [<<] Go back, I'll Claude it
```

**Merge confirmation:**
```
Merge `auth` → `main` will:
• Merge branch and push
• Close tmux session
• Delete /dev/project-auth
• Archive topic

Continue?
[Yes, finish] [x] Cancel
```

**Delete confirmation:**
```
`[!]` Delete branch `auth` WITHOUT merging?

This will:
• Close tmux session
• Delete /dev/project-auth
• Delete branch `auth`
• Archive topic

All uncommitted work will be LOST.

[Yes, delete] [x] Cancel
```

**Results:**

| Outcome | Message |
|---------|---------|
| Merge + push OK | `[v]` Branch auth merged and cleaned up |
| Merge OK, push failed | `[v]` Branch auth merged and cleaned up<br>`[!]` Push failed. Run \`git push\` manually. |
| Conflicts | `[!]` Merge conflicts. Resolve and run /branch_finish again |
| Uncommitted in target | `[!]` Uncommitted changes in main. Commit or stash first. |
| Delete OK | `[v]` Branch auth deleted |

### `/thread_create` warning

Show if ≥1 non-General thread exists without worktree_path.

```
`[!]` Topic without isolation exists. Use /branch_create for isolated work.

[Create in main anyway] [/branch_create] [x] Cancel
```

## Data Model

### ThreadInfo changes

```python
@dataclass
class ThreadInfo:
    thread_id: int | None
    name: str

    # Existing fields...
    session_id: str | None = None
    jsonl_path: str | None = None
    # ...

    # NEW: worktree support
    worktree_path: str | None = None  # None = main repo directory
    base_branch: str | None = None    # Branch this worktree was created from
    archived: bool = False            # True = topic closed after /branch_finish
```

### Default branch detection

Don't hardcode "main". Detect default branch:

```bash
# Try remote HEAD first
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'

# Fallback to local config
git config --get init.defaultBranch

# Fallback to "main"
```

### Config persistence

`.config.json`:
```json
{
  "projects": {
    "myproject": {
      "chat_id": -100123456,
      "cwd": "/dev/myproject",
      "threads": {
        "null": {
          "name": "main"
        },
        "456": {
          "name": "auth",
          "worktree_path": "/dev/myproject-auth",
          "base_branch": "main"
        }
      }
    }
  }
}
```

## Conventions

### Naming

| Input | Topic name | Branch | Directory |
|-------|------------|--------|-----------|
| `/branch_create` | magic name | `{magic}` | `/dev/project-{magic}` |
| `/branch_create auth` | auth | `auth` | `/dev/project-auth` |
| `/branch_create fix-login` | fix-login | `fix-login` | `/dev/project-fix-login` |

### Name sanitization

- Slashes replaced silently: `feature/auth` → `feature-auth`
- Invalid chars removed: only `[a-zA-Z0-9_-]` allowed

### Name length limit

tmux session format: `claude-{project}-{name}`

**Project name limit (checked at /start):**
```
if len(project_name) > 35:
    `[!]` Project name too long (max 35 chars). Rename group or use /register_dir with shorter name.
```

**Branch name limit:**
```
max_name_length = 45 - len(project_name)
```

| Project | Max branch name |
|---------|-----------------|
| codogram (8) | 37 chars |
| my-long-project (15) | 30 chars |
| very-long-project-name-here (27) | 18 chars |
| max-length-project-name-here-xx (35) | 10 chars |

Error: `` `[x]` Name too long (max 37 chars for this project) ``

### Magic names exhausted

If all magic names taken (arcane, mystic, celestial...):
- Try with suffix: `arcane-2`, `arcane-3`...
- Find first available

### Directory location

Worktrees created adjacent to main project:
```
/dev/
├── project/           ← main
├── project-auth/      ← worktree
└── project-fix-bug/   ← worktree
```

### Detecting worktree topics

- `worktree_path` is None → main directory
- `worktree_path` is set → worktree topic

## Git Operations

### Create worktree

```bash
# From main
git worktree add -b auth ../project-auth main

# From another branch
git worktree add -b new-feature ../project-new-feature feature-x
```

### Merge and cleanup

**Cleanup order is important:**

```bash
# target_branch = user selection (main, feature-x, etc.)

# 1. Check main directory for uncommitted changes first
cd /dev/project
git status --porcelain
# If dirty → `[!]` Uncommitted changes. Commit or stash first.

# 2. Switch to target branch
git checkout {target_branch}

# 3. Merge
git merge auth
# If conflicts → stop, user resolves, runs /branch_finish again

# 4. Push target branch (if success)
git push origin {target_branch}
# If push fails → `[!]` Push failed. Run `git push` manually.
# Continue cleanup regardless of push result

# 5. Kill tmux FIRST (Claude stops writing to worktree)
tmux kill-session -t claude-project-auth

# 6. Remove worktree
git worktree remove ../project-auth

# 7. Delete branch
git branch -d auth

# 8. Archive topic (close + folder icon)
await bot.close_forum_topic(chat_id, thread_id)
await bot.edit_forum_topic(chat_id, thread_id, icon_custom_emoji_id="5357315181649076022")  # 📁
```

**Idempotent cleanup:**

Each step checks if already done:
- tmux: check if session exists before kill
- worktree: check if directory exists before remove
- branch: check if branch exists before delete
- topic: check if not already archived

This allows retry after partial failure.

### Delete without merge

```bash
git worktree remove --force ../project-auth
git branch -D auth
```

## Archived Topics

After `/branch_finish`, thread is archived but kept in `project.threads`:

```python
thread.archived = True
thread.worktree_path = None  # directory deleted
# thread.name, thread.base_branch preserved
```

If user runs `/start` from archived topic:

```
`[!]` Topic archived.

[Create new git worktree] [x] Cancel
```

On "Create new git worktree":
1. `reopen_forum_topic`
2. Create worktree with same name
3. `thread.archived = False`

## Edge Cases

1. **Worktree directory already exists** → `[x]` Directory /dev/project-auth already exists. Use different name.
2. **Branch already exists** → `[x]` Branch 'auth' already exists. Use different name or delete branch.
3. **Merge conflicts** → stop, notify user, wait for /branch_finish retry
4. **Tmux session won't die** → force kill, log warning
5. **Topic archiving fails** → log warning, continue cleanup
6. **Worktree deleted manually** → skip worktree removal, continue with branch/tmux/topic cleanup
7. **Uncommitted changes in target branch** → `[!]` before merge, block until resolved
8. **Push fails** → `[!]` warning, continue cleanup (merge already done locally)
9. **No remote origin** → skip push, no warning
10. **Race condition** → two `/branch_create auth` simultaneously: first wins, second gets error "Branch already exists"
11. **Name too long** → `[x]` with max allowed length for this project
12. **Base branch deleted** → don't show in merge popup, only show main

## Future Considerations

- `/branch_list` — show all worktree topics with status
- Auto-cleanup of orphaned worktrees on bot restart
- PR creation instead of merge (`/branch_pr`)
