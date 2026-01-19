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
| `/finish_chat` | `/finish`, `/archive`, `/fc` |
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
[?] Creating chat from:
📁 ~/dev/codogram/.worktrees/feature-x
🌿 feature-x

To branch from main, run /new_chat in General

[Create here]  [Create isolated]  [<< Cancel]
```

**From General (main):**
```
[?] Creating chat from:
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

| Scenario | User Prompts |
|----------|--------------|
| Same dir | 2 (context → name) |
| Isolated, clean | 2 (context → name) |
| Isolated + uncommitted | 3 (context → uncommitted → name) |
| No git repo | 1 (name only) |

Note: "Steps" = visible user prompts, actual creation happens automatically after name.

### Dropped Flows

**"Non-worktree threads exist" warning** — removed. The new unified flow makes this unnecessary:
- User explicitly chooses "Create here" vs "Create isolated"
- No need to warn about mixing approaches

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
├── new_chat.py      ← ALL logic (complete flow, name handling, creation)
├── finish_chat.py   ← renamed from finish.py
├── threads.py       ← pure alias → new_chat (no callbacks)
├── branches.py      ← pure alias → new_chat (no callbacks)
└── ...
```

### new_chat.py Contains

- `require_forum_group` check
- Step 1: context display + choice keyboard
- Step 2: uncommitted changes dialog (if isolated)
- Step 3: name prompt + magic name handling
- Actual creation (calls `create_thread_with_session` or `do_branch_create`)
- All callback handlers (`nc_*` prefix)

### Callback Data

**New (all in new_chat.py):**
- `nc_here` — create in current directory
- `nc_isolated` — create isolated branch
- `nc_cancel` — cancel flow
- `nc_magic` — generate magic name
- `nc_uncommitted_clean:{name}` — create from last commit
- `nc_uncommitted_commit:{name}` — ask Claude to commit first

**Dropped (remove entirely):**
- `create_magic:thread` / `create_magic:branch` — replaced by `nc_magic`
- `create_cancel` — replaced by `nc_cancel`
- `bc_base:*`, `bc_create:*`, `bc_commit:*` — moved to nc_* equivalents
- `thread_create_confirm`, `branch_create_redirect` — removed

### Alias Handlers

```python
# handlers/threads.py
from .new_chat import cmd_new_chat

@router.message(Command("thread", "thread_create"))
async def cmd_thread(message, telegram_queue):
    await cmd_new_chat(message, telegram_queue)
```

Pure delegation, zero logic, zero callbacks.

### Changes Required

1. **handlers/new_chat.py** — new file with complete flow
2. **handlers/threads.py** — strip to pure alias (remove all callbacks)
3. **handlers/branches.py** — strip to pure alias (remove all callbacks)
4. **handlers/finish.py** → **handlers/finish_chat.py** — rename, add aliases
5. **handlers/sessions.py** — add `clear_context` as primary, `reset_chat` as primary
6. **handlers/create_flow.py** — remove or simplify (no longer needed for thread/branch)
7. **keyboards/create_flow.py** — update for nc_* callbacks
8. **services/menu.py** — new command order and descriptions
9. **strings.py** — new constants for /new_chat flow and /help
10. **handlers/settings.py** — update /help handler
11. **main.py** — register new_chat router, update finish import
12. **E2E tests** — update docs/e2e/commands/ for new commands

