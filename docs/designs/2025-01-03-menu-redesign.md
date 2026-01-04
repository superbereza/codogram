# Menu Redesign and /finish Command

## Overview

Reorganize bot menu for better usability, add short command aliases, and unify topic archival logic in `/finish`.

## New Menu Structure

```
Everyday:
/esc         - Cancel current operation
/clear       - Clear context, start fresh
/auto_accept - Toggle auto-accept mode

Create:
/thread      - New topic in project directory
/branch      - New isolated feature branch + topic

Complete:
/finish      - Merge branch, archive topic

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

## New Fields in ThreadInfo

```python
@dataclass
class ThreadInfo:
    # ... existing fields ...

    archived: bool = False
    branch_name: str | None = None  # Git branch name (None = regular topic)
```

- `branch_name` present → worktree topic
- `branch_name` = None → regular topic
- `archived` = True → topic is closed

## /finish Logic

### In worktree topic (branch_name exists):

1. Existing merge confirmation flow
2. Merge branch → target
3. Delete worktree directory
4. Delete git branch
5. Kill tmux session
6. Close Telegram topic + archive icon
7. Set `archived = True`, keep `branch_name`

### In regular topic (branch_name = None):

1. Show confirmation: "Archive this topic?"
2. Kill tmux session
3. Close Telegram topic + archive icon
4. Set `archived = True`

### In General (thread_id = None):

- Respond: "Nothing to finish here. Use /clear to start fresh."

## /start in Archived Topic

User reopens topic manually in Telegram UI before /start.

### Regular topic (branch_name = None):

1. Set `archived = False`
2. Remove archive icon
3. Launch Claude in `project.cwd`

### Worktree topic (branch_name exists):

1. Show inline keyboard:
   ```
   "Continue in new branch or main directory?"
   [New branch] [Main directory]
   ```

2. **[New branch]:**
   - `git checkout main`
   - `git branch {branch_name}`
   - `git worktree add .worktrees/{name} {branch_name}`
   - Set `archived = False`
   - Remove archive icon
   - Launch Claude in worktree

3. **[Main directory]:**
   - Set `branch_name = None` (convert to regular topic)
   - Set `archived = False`
   - Remove archive icon
   - Launch Claude in `project.cwd`

## Edge Cases

| Situation | Solution |
|-----------|----------|
| Branch with same name exists | Error: "Branch exists. Delete it or use /branch for new name" |
| Worktree directory remains | Delete and recreate |
| Topic deleted in Telegram | Catch error, remove thread from config |
| Merge conflicts | Show error, ask to resolve manually |

## Implementation Changes

| File | Changes |
|------|---------|
| `session_manager.py` | Add `archived`, `branch_name` to ThreadInfo + save/load |
| `main.py` | New menu order and descriptions |
| `bot.py` | Command aliases, /finish for regular topics, /start for archived |

## Archive Icon

Using existing icon from branch_finish:
```python
icon_custom_emoji_id = "5357315181649076022"  # archive folder
```
