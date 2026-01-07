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
  create_flow.py          # State and result types
    - CreateType (enum): BRANCH, THREAD
    - CreateFlowState (dataclass): type, thread_id
    - CreateAction (enum): SHOW_PROMPT, CREATE, ERROR
    - CreateResult (dataclass): action, name, error

services/
  create_flow.py          # Business logic
    - CreateFlowService
      - start_flow(type, has_name) -> CreateResult
      - get_magic_name(project) -> str
      - validate_name(name, project, type) -> (sanitized, error)
      - create(type, project, name, ...) -> delegates to branch/launch service

handlers/
  branches.py             # Thin router, builds UI from CreateResult
  threads.py              # Thin router, builds UI from CreateResult
  create_flow.py          # NEW: shared callbacks and message handler
    - on_magic_name(callback)
    - on_cancel_prompt(callback)
    - handle_name_message(message) - called from messages.py

keyboards/
  create_flow.py          # NEW: keyboard builders
    - build_name_prompt_keyboard(type)
```

### State Management

New module `domain/create_flow.py`:

```python
@dataclass
class CreateFlowState:
    type: CreateType  # BRANCH or THREAD
    thread_id: int | None

# Module-level state (like _flow_state in common.py)
_create_state: dict[int, CreateFlowState] = {}  # chat_id -> state

def get_state(chat_id: int) -> CreateFlowState | None
def set_state(chat_id: int, state: CreateFlowState) -> None
def clear_state(chat_id: int) -> None
def has_pending_create(chat_id: int) -> bool
```

### Service Layer

`services/create_flow.py`:

```python
class CreateFlowService:
    def should_show_prompt(self, name_arg: str | None) -> bool:
        """Returns True if no name provided."""
        return name_arg is None

    def get_magic_name(self, project) -> str:
        """Generate random magic name not used by project."""
        existing = {t.name for t in project.threads.values()}
        return get_random_magic_name(existing)

    def validate_name(self, name: str, project, create_type: CreateType) -> tuple[str | None, str | None]:
        """Validate and sanitize name. Returns (sanitized, error)."""
        sanitized = sanitize_branch_name(name)
        if not sanitized:
            return None, "`[x]` Invalid name"

        # Check length (same for both)
        max_len = max_branch_name_length(project.project_name)
        if len(sanitized) > max_len:
            return None, f"`[x]` Name too long (max {max_len} chars)"

        # Check uniqueness
        existing = {t.name for t in project.threads.values()}
        if sanitized in existing:
            return None, f"`[x]` Name `{sanitized}` already used"

        return sanitized, None
```

### Handler Layer

Handlers stay thin - delegate to service, build UI:

```python
# handlers/branches.py
async def cmd_branch_create(message, queue):
    # ... existing checks (forum, project, git repo) ...

    args = message.text.split(maxsplit=1)
    name_arg = args[1] if len(args) > 1 else None

    if service.should_show_prompt(name_arg):
        set_state(chat_id, CreateFlowState(CreateType.BRANCH, thread_id))
        await queue.reply(message, "Branch name?\n\nSend name or pick random",
                         reply_markup=build_name_prompt_keyboard(CreateType.BRANCH))
        return

    # Has name - validate and proceed
    name, error = service.validate_name(name_arg, project, CreateType.BRANCH)
    if error:
        await queue.reply(message, error)
        return

    # ... rest of branch creation flow (uncommitted changes check, etc.) ...
```

### Unified Validation Rules

Same rules for both branch and thread:
1. sanitize_branch_name() - lowercase, spaces→dashes, remove invalid chars
2. Check max length based on project name
3. Check name not already used by existing thread

Branch-specific checks (after name validation):
- Git repo required
- Uncommitted changes handling
- Worktree directory check

## File Changes

**New files:**
- `src/codogram/domain/create_flow.py` - state and types
- `src/codogram/services/create_flow.py` - business logic
- `src/codogram/handlers/create_flow.py` - shared callbacks
- `src/codogram/keyboards/create_flow.py` - keyboard builder

**Modified files:**
- `src/codogram/handlers/branches.py` - use service, show prompt
- `src/codogram/handlers/threads.py` - use service, show prompt
- `src/codogram/handlers/messages.py` - check create state before routing
- `src/codogram/handlers/__init__.py` - register create_flow router

**Removed from common.py:**
- Move `_flow_state` usage for create flow to new domain module
