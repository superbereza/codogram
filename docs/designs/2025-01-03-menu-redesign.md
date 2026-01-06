# Menu Redesign and /finish Command

## Overview

Reorganize bot menu for better usability, add short command aliases, and unify topic archival logic in `/finish`.

## New Menu Structure

```
Everyday:
/esc         - Cancel current operation
/auto_accept - Toggle auto-accept mode

Create:
/thread      - New topic in project directory
/branch      - New isolated feature branch + topic

Complete:
/clear       - Clear context, start fresh
/finish      - Merge branch, archive topic (keeps worktree)

Settings:
/start       - Connect Claude or show status
/settings    - View current settings
/restart     - Force restart Claude
/my_chat_id  - Show chat and thread IDs

Help:
/help        - List all commands
```

## Hidden Commands

| Command | Behavior |
|---------|----------|
| `/new` | Alias for `/clear` |
| `/thread_create` | Alias for `/thread` |
| `/branch_create` | Alias for `/branch` |
| `/thread_delete` | Responds "Use /finish" |
| `/branch_finish` | Responds "Use /finish" |

## ThreadInfo Changes

```python
@dataclass
class ThreadInfo:
    # ... existing fields ...
    archived: bool = False  # NEW: topic is closed via /finish
```

**Branch detection** (no new field needed):
- `worktree_path != None` → worktree/branch topic
- `worktree_path == None` → regular topic
- `name` field already stores branch name for worktree topics

**States:**
- `archived = False` → active topic
- `archived = True` → closed via /finish (can reopen with /start)

## /finish Logic

### In worktree topic (worktree_path != None):

1. Existing merge confirmation flow
2. Merge branch → target
3. Kill tmux session (frees RAM)
4. Close Telegram topic + archive icon
5. Set `archived = True`, keep `branch_name`

**Note:** Worktree and git branch are NOT deleted. This allows:
- Easy restart via `/start` in archived topic
- Session resume with full context
- Explicit cleanup via `/cleanup` when ready

### In regular topic (worktree_path = None):

1. Show confirmation: "Archive this topic?"
2. Kill tmux session
3. Close Telegram topic + archive icon
4. Set `archived = True`

### In General (thread_id = None):

- Respond: "Nothing to finish here. Use /clear to start fresh."

## /start in Archived Topic

User reopens topic manually in Telegram UI before /start.

### Regular topic (worktree_path = None):

1. Set `archived = False`
2. Remove archive icon
3. Launch Claude in `project.cwd`

### Worktree topic (worktree_path != None):

Since worktree is preserved after /finish, restart is simple:

1. Set `archived = False`
2. Remove archive icon
3. Create tmux session in worktree_path
4. Resume Claude: `claude --resume {session_id}` (if exists)
5. Or fresh start: `claude` (if no session)

## /cleanup Command

See separate design: `2026-01-05-cleanup-command.md`

## Edge Cases

| Situation | Solution |
|-----------|----------|
| Branch with same name exists | Error: "Branch exists. Delete it or use /branch for new name" |
| Worktree missing on /start | Recreate worktree from existing branch |
| Topic deleted in Telegram | Catch error, set `deleted = True` in config |
| Merge conflicts | Show error, ask to resolve manually |

## Implementation Changes

| File | Changes |
|------|---------|
| `session_manager.py` | Add `archived` field to ThreadInfo |
| `main.py` | New menu order and descriptions |
| `handlers/start.py` | Resume logic, tmux running check |
| `handlers/finish.py` | Unified /finish (don't delete worktree) |
| `launch_animation.py` | Add `session_id`, `cwd` params |

Note: `deleted` field and `/cleanup` command in separate design.

## Archive Icon

Using existing icon from branch_finish:
```python
icon_custom_emoji_id = "5357315181649076022"  # archive folder
```
