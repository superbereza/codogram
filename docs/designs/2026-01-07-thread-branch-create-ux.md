# Thread/Branch Create UX

## Problem

Currently `/branch` and `/thread` without argument auto-create with random magic name. User doesn't get to choose or see what name will be used.

## Solution

Show prompt with option to pick random name or send custom name.

## User Flow

### Without argument (new behavior)

```
User: /branch
Bot:  Branch name?
      Send name or pick random
      [🔮 Magic name] [[<<] Go back]
```

**Actions:**
- `🔮 Magic name` → generate random name, create branch, delete prompt
- `[<<] Go back` → delete prompt
- User sends text → sanitize, validate, create branch, delete prompt

### With argument (unchanged)

```
User: /branch mystic
Bot:  creates branch "mystic" directly
```

### Same UX for /thread

Replace "Branch" with "Thread" in messages.

## State Management

Use existing `_flow_state`:

```python
_flow_state[chat_id] = {
    "state": "awaiting_branch_name",  # or "awaiting_thread_name"
    "thread_id": message.message_thread_id,
}
```

**State cleared when:**
- User sends name → create, clear
- User clicks 🔮 Magic name → create with random, clear
- User clicks [<<] Go back → delete message, clear
- User sends other command → execute command, clear

## Name Validation

**Sanitization** (existing `git_utils.sanitize_branch_name`):
- lowercase
- spaces and `/` → dashes
- remove all except `a-z`, `0-9`, `_`, `-`

**Validation errors:**
- Empty after sanitization → `[x]` Invalid name
- Too long → `[x]` Name too long (max N chars)
- Branch exists → `[x]` Branch `name` already exists
- Worktree dir exists → `[x]` Directory already exists
- Thread name taken → `[x]` Thread `name` already exists

## File Changes

**`handlers/branches.py`:**
- `cmd_branch_create`: show prompt when no argument
- New callback `on_magic_name_branch`

**`handlers/threads.py`:**
- `cmd_thread_create`: show prompt when no argument
- New callback `on_magic_name_thread`

**`handlers/messages.py`:**
- Check `_flow_state` for `awaiting_branch_name` / `awaiting_thread_name`
- If set → validate, sanitize, create
- If not → send to tmux as usual

**`handlers/common.py`:**
- Optional shared `show_name_prompt()` for DRY
