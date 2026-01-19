# Command Merge & Menu Simplification

## Overview

Merge `/thread` and `/branch` commands into unified `/new_chat`. Simplify menu naming for better UX.

## Command Naming & Aliases

### Telegram Menu (exact order)

```
esc           — Send Esc, stop current operation
shift_tab     — Cycle Claude approval mode
auto_accept   — Accept every Claude permission 🚧
new_chat      — Create new chat: topic & Claude session
finish_chat   — Archive chat and stop Claude
start         — Connect or resume
settings      — Show settings
clear_context — Clear current Claude context
reset_chat    — Restart Claude process
get_debug_ids — Debug info
help          — Show help
hard_reset    — Full project reset
```

### Aliases

| Primary | Aliases |
|---------|---------|
| `/new_chat` | `/thread`, `/branch`, `/nc`, `/thread_create`, `/branch_create` |
| `/finish_chat` | `/archive_chat`, `/finish`, `/archive`, `/fc` |
| `/clear_context` | `/clear`, `/new` |
| `/reset_chat` | `/restart` |
| `/hard_reset` | `/reset_all` |

### Menu Order Logic

1. Operations (esc, shift_tab, auto_accept) — frequent actions at top
2. Chats (new_chat, finish_chat, start) — main workflow
3. Settings (settings)
4. Context/process (clear_context, reset_chat)
5. Debug (get_debug_ids)
6. Help and destructive (help, hard_reset) — at bottom

## `/new_chat` Flow

### Step 1: Context + Choice

Shows current directory and branch, offers create options.

**From worktree topic:**
```
Creating chat from:
📁 ~/dev/codogram/.worktrees/feature-x
🌿 feature-x

To branch from main, run /new_chat in General

[Create here]  [Create isolated]  [<< Cancel]
```

**From General (main):**
```
Creating chat from:
📁 ~/dev/codogram
🌿 main

[Create here]  [Create isolated]  [<< Cancel]
```

**No git repo:**
Skip to name prompt, "Create isolated" hidden.

### Step 2: Uncommitted Changes (isolated only)

Only shown when creating isolated branch AND uncommitted changes exist.

```
[!] Uncommitted changes detected

[Create from last commit]  [Commit first]  [<< Go back]
```

### Step 3: Name

```
Chat name?

Send name or pick random

[🔮 Magic name]  [<< Go back]
```

### Flow Summary

| Scenario | Steps |
|----------|-------|
| Same dir | 2 (context → name) |
| Isolated, clean | 3 (context → name) |
| Isolated + uncommitted | 4 (context → uncommitted → name) |
| No git repo | 1 (name only) |

## `/help` Content

```
Troubleshoot

If bot isn't responding, try /reset_chat — it's safe for context.

To wipe project and start fresh: /hard_reset. 🚨 Dangerous zone!

─────────────────

Chats
/new_chat — create new chat: topic & Claude session
/finish_chat — archive chat and stop Claude
/start — connect or resume
/reset_chat — restart Claude process

Context
/clear_context — clear current Claude context

Operations
/esc — send Esc, stop current operation
/shift_tab — cycle Claude approval mode
/auto_accept — accept every Claude permission 🚧

Settings
/settings — show settings
/get_debug_ids — debug info

[Close]
```

Close button deletes the help message.

## Implementation

### File Structure

```
handlers/
├── new_chat.py      ← ALL logic (merged from threads + branches)
├── finish_chat.py   ← rename/update from finish.py
├── threads.py       ← pure alias → new_chat
├── branches.py      ← pure alias → new_chat
└── ...
```

### new_chat.py Contains

- `require_forum_group` check (from common.py)
- Step 1: context display + choice keyboard
- Step 2: uncommitted changes dialog (if isolated)
- Step 3: name prompt
- Topic creation + Claude launch
- All callback handlers (`nc_*` prefix)

### Alias Handlers

```python
# handlers/threads.py
from .new_chat import cmd_new_chat

@router.message(Command("thread", "thread_create"))
async def cmd_thread(message, telegram_queue):
    await cmd_new_chat(message, telegram_queue)
```

Pure delegation, zero logic.

### Changes Required

1. **handlers/new_chat.py** — new file with merged logic
2. **handlers/threads.py** — strip to alias only
3. **handlers/branches.py** — strip to alias only
4. **handlers/finish.py** — rename to finish_chat.py, add aliases
5. **handlers/sessions.py** — update `/new` to alias `/clear_context`
6. **domain/menu.py** — new command order and descriptions
7. **strings.py** — new constants for `/new_chat` flow and `/help`
8. **handlers/settings.py** — update `/help` handler

### Callback Data Migration

| Old | New |
|-----|-----|
| `tc_*` (thread create) | `nc_*` |
| `bc_*` (branch create) | `nc_*` |

### Deprecation Approach

- Aliases work silently (no warnings)
- Old names kept indefinitely for muscle memory
- Docs and `/help` show only primary names
