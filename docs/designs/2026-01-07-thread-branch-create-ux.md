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

## Architecture

Following layered architecture from CLAUDE.md:

```
domain/
  create_flow.py          # Types only (no state)
    - CreateType (enum): BRANCH, THREAD

services/
  create_flow.py          # Business logic + singleton
    - CreateFlowService
      - should_show_prompt(name_arg) -> bool
      - get_magic_name(project) -> str
      - validate_name(name, project) -> (sanitized, error)
      - check_branch_preconditions(project, name) -> (can, error, warning)
    - create_flow_service  # module-level singleton

middleware/
  clear_create_state.py   # Clears state on any command
    - ClearCreateStateMiddleware

handlers/
  common.py               # State with (chat_id, thread_id) key
    - get_flow_state(chat_id, thread_id)
    - set_flow_state(chat_id, thread_id, state)
    - clear_flow_state(chat_id, thread_id)
    - clear_flow_state_by_type(chat_id, thread_id, type)
  create_flow.py          # Shared callbacks and name input
    - on_create_cancel(callback)
    - on_create_magic(callback)
    - handle_name_input(message) -> bool
  branches.py             # Thin router
  threads.py              # Thin router

keyboards/
  create_flow.py          # Keyboard builder + constants
    - CALLBACK_MAGIC_PREFIX = "create_magic:"
    - CALLBACK_CANCEL = "create_cancel"
    - build_name_prompt_keyboard(type)
```

### State Management

Reuse existing `_flow_state` in `handlers/common.py` with new key structure:

```python
# Key: (chat_id, thread_id) instead of just chat_id
_flow_state: dict[tuple[int, int | None], dict] = {}

# State structure for create flow:
{
    "type": "awaiting_create_name",
    "create_type": "branch"  # or "thread"
}
```

**Why (chat_id, thread_id)?**
- Different topics in same chat don't conflict
- `/branch` in topic A doesn't affect `/thread` in topic B

### Middleware Layer

`ClearCreateStateMiddleware` runs before all handlers:

```
User message → Middleware → Handler
                  ↓
         if starts with "/"
         and state type == "awaiting_create_name"
                  ↓
            clear state
```

**Why middleware?**
- Single place, all commands covered
- New handlers automatically protected
- Handlers don't need to know about create flow state

**What it clears:**
- Only `awaiting_create_name` state
- Other state types (`thread_create_pending`) untouched

### Service Layer

```python
class CreateFlowService:
    def should_show_prompt(self, name_arg: str | None) -> bool:
        """Returns True if no name or whitespace only."""
        if name_arg is None:
            return True
        return not name_arg.strip()

    def get_magic_name(self, project) -> str:
        """Generate random magic name not used by project."""
        existing = {t.name for t in project.threads.values()}
        return get_random_magic_name(existing)

    def validate_name(self, name: str, project) -> tuple[str | None, str | None]:
        """Validate and sanitize name. Returns (sanitized, error)."""
        # 1. Sanitize
        # 2. Check length
        # 3. Check uniqueness
        ...

    def check_branch_preconditions(self, project, name: str) -> tuple[bool, str | None, str | None]:
        """Check git repo and uncommitted changes.
        Returns (can_create, error, warning).
        - error: fatal, cannot proceed
        - warning: can proceed with confirmation (uncommitted changes)
        """
        ...

# Module-level singleton
create_flow_service = CreateFlowService()
```

### Unified Validation Rules

Same rules for both branch and thread:
1. `sanitize_branch_name()` - lowercase, spaces→dashes, remove invalid chars
2. Check max length based on project name
3. Check name not already used by existing thread

Branch-specific checks (in service, after name validation):
- Git repo required → error
- Uncommitted changes → warning (show options)

## File Changes

**New files:**
- `src/codogram/domain/create_flow.py` - CreateType enum only
- `src/codogram/services/create_flow.py` - business logic + singleton
- `src/codogram/middleware/clear_create_state.py` - clears state on commands
- `src/codogram/handlers/create_flow.py` - shared callbacks
- `src/codogram/keyboards/create_flow.py` - keyboard builder + constants

**Modified files:**
- `src/codogram/handlers/common.py` - state functions with (chat_id, thread_id) key
- `src/codogram/handlers/branches.py` - use service, show prompt
- `src/codogram/handlers/threads.py` - use service, show prompt
- `src/codogram/handlers/messages.py` - check create state before routing
- `src/codogram/handlers/__init__.py` - register create_flow router
- `src/codogram/main.py` - register middleware
