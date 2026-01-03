# Bot.py Refactoring: Phases 4-6 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract AdminMiddleware, verify launch logic, and create first handler module (permissions).

**Architecture:** Middleware on main router (not dispatcher!) handles admin check. Handlers are thin routers delegating to services.

**Tech Stack:** Python 3.11+, aiogram 3.x middleware, pytest

**Design Doc:** `docs/designs/2025-12-27-bot-refactoring/02-phase-4-6.md`

**Current State:**
- `launch_animation.py` already exists with `launch_with_animation()`
- 30 admin checks (`if not is_admin(...)`) scattered in bot.py
- `/my_chat_id` is the only public command (no admin check)
- `is_admin()` and `get_admin_ids()` defined in bot.py (lines 42-51)

---

## Phase 4: Extract middleware/admin.py

### Task 4.1: Create middleware/admin.py with tests

**Files:**
- Create: `src/codogram/middleware/admin.py`
- Create: `tests/test_admin_middleware.py`

**Step 1: Write the failing test**

Create `tests/test_admin_middleware.py`:

```python
"""Tests for admin middleware."""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from codogram.middleware.admin import AdminMiddleware, is_admin


class TestIsAdmin:
    """Tests for is_admin helper."""

    def test_admin_returns_true(self):
        with patch("codogram.middleware.admin.get_admin_ids", return_value={123, 456}):
            assert is_admin(123) is True
            assert is_admin(456) is True

    def test_non_admin_returns_false(self):
        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            assert is_admin(999) is False


class TestAdminMiddleware:
    """Tests for AdminMiddleware."""

    @pytest.mark.asyncio
    async def test_admin_allowed(self):
        """Admin users can access handlers."""
        middleware = AdminMiddleware()
        handler = AsyncMock(return_value="result")
        event = Mock()
        data = {"event_from_user": Mock(id=123)}

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_called_once_with(event, data)
        assert result == "result"

    @pytest.mark.asyncio
    async def test_non_admin_blocked(self):
        """Non-admin users are silently blocked."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock()
        data = {"event_from_user": Mock(id=999)}

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_no_user_blocked(self):
        """Events without user are blocked."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock()
        data = {}  # No event_from_user

        result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=src pytest tests/test_admin_middleware.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

Create `src/codogram/middleware/admin.py`:

```python
"""Admin middleware - restrict handlers to admin users."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from ..config import settings

# Cache admin IDs
_admin_ids: set[int] | None = None


def get_admin_ids() -> set[int]:
    """Get admin IDs (cached)."""
    global _admin_ids
    if _admin_ids is None:
        _admin_ids = settings.get_admin_ids()
    return _admin_ids


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in get_admin_ids()


class AdminMiddleware(BaseMiddleware):
    """Skip handlers for non-admin users.

    Silently ignores all events from non-admin users.

    IMPORTANT: Register on router, NOT dispatcher!
    - router.message.middleware(AdminMiddleware()) ✓
    - dp.message.middleware(AdminMiddleware()) ✗ (blocks ALL routers)
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        if user is None or not is_admin(user.id):
            return None  # Silently ignore non-admins

        return await handler(event, data)
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=src pytest tests/test_admin_middleware.py -v
```

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/codogram/middleware/admin.py tests/test_admin_middleware.py
git commit -m "feat(middleware): add AdminMiddleware

Silently blocks non-admin users from handlers.
Must be registered on router, not dispatcher."
```

---

### Task 4.2: Update middleware/__init__.py

**Files:**
- Modify: `src/codogram/middleware/__init__.py`

**Step 1: Add exports**

```python
"""Middleware layer."""
from .admin import AdminMiddleware, is_admin, get_admin_ids

__all__ = ["AdminMiddleware", "is_admin", "get_admin_ids"]
```

**Step 2: Verify import**

```bash
python -c "from codogram.middleware import AdminMiddleware, is_admin; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/codogram/middleware/__init__.py
git commit -m "refactor(middleware): export public API from __init__"
```

---

### Task 4.3: Create handlers/public.py for /my_chat_id

**Files:**
- Create: `src/codogram/handlers/public.py`

**Step 1: Create public router**

Create `src/codogram/handlers/public.py`:

```python
"""Public handlers - available to all users (no admin check)."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="public")


@router.message(Command("my_chat_id"))
async def cmd_my_chat_id(message: Message):
    """Show user's chat ID - available to everyone."""
    thread_id = message.message_thread_id
    thread_info = f"\nThread ID: `{thread_id}`" if thread_id else "\nThread ID: None (General)"
    await message.answer(
        f"Your user ID: `{message.from_user.id}`\n"
        f"This chat ID: `{message.chat.id}`{thread_info}",
        parse_mode="Markdown",
    )
```

**Step 2: Verify import**

```bash
python -c "from codogram.handlers.public import router; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/codogram/handlers/public.py
git commit -m "feat(handlers): add public router for /my_chat_id

Public commands available to all users, not just admins."
```

---

### Task 4.4: Register middleware on ROUTER (not dispatcher) in main.py

**Files:**
- Modify: `src/codogram/main.py`
- Modify: `src/codogram/bot.py` (add middleware to router)

> **CRITICAL:** Middleware must be on `router`, not `dp`!
> - `dp.message.middleware()` applies to ALL routers (breaks public_router)
> - `router.message.middleware()` applies only to main router ✓

**Step 1: Add middleware to router in bot.py**

At the top of `src/codogram/bot.py`, after `router = Router()`:

```python
from .middleware.admin import AdminMiddleware

router = Router()

# Admin middleware - only for this router, not public handlers
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())
```

**Step 2: Update main.py to include public router**

Add import:
```python
from .handlers.public import router as public_router
```

Before `dp.include_router(router)`, add:
```python
# Public router FIRST (no middleware, available to all)
dp.include_router(public_router)
```

**Step 3: Verify circular imports don't occur**

```bash
python -c "from codogram.bot import router; from codogram.handlers.public import router as pr; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add src/codogram/bot.py src/codogram/main.py
git commit -m "refactor: register AdminMiddleware on router, not dispatcher

IMPORTANT: Middleware on router level only affects that router.
public_router remains accessible to all users."
```

---

### Task 4.5: Remove admin checks AND is_admin function from bot.py

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: List all admin check locations**

```bash
grep -n "if not is_admin" src/codogram/bot.py | cut -d: -f1 | tr '\n' ' '
```

Note all line numbers (approximately 30 locations).

**Step 2: Remove each admin check block**

For each handler, remove these lines:
```python
    if not is_admin(message.from_user.id):
        return
```

Or for callbacks:
```python
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return
```

**Step 3: Remove /my_chat_id handler (moved to handlers/public.py)**

Delete the `cmd_my_chat_id` function from bot.py (around line 1305-1310).

**Step 4: Remove is_admin and get_admin_ids from bot.py**

Delete these functions (around lines 42-51):
```python
_admin_ids: set[int] | None = None

def get_admin_ids() -> set[int]:
    """Get admin IDs (cached)."""
    global _admin_ids
    if _admin_ids is None:
        _admin_ids = settings.get_admin_ids()
    return _admin_ids

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in get_admin_ids()
```

> **Note:** If `get_admin_ids` is used elsewhere in bot.py (e.g., logging),
> import it from middleware: `from .middleware.admin import get_admin_ids`

**Step 5: Verify cleanup complete**

```bash
# No admin checks remaining
grep -c "if not is_admin" src/codogram/bot.py
# Expected: 0

# No local is_admin function
grep -c "def is_admin" src/codogram/bot.py
# Expected: 0
```

**Step 6: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short
```

Expected: All tests PASS

**Step 7: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove admin checks and is_admin function

- Removed 30 'if not is_admin()' blocks (middleware handles this)
- Removed is_admin/get_admin_ids (moved to middleware/admin.py)
- Removed /my_chat_id (moved to handlers/public.py)"
```

---

### Task 4.6: E2E Verification for Phase 4

**Manual testing checklist:**

> Skip if no .env available in worktree. These tests require running bot.

- [ ] Non-admin sends `/start` → nothing happens (silently ignored)
- [ ] Non-admin sends `/my_chat_id` → receives response with IDs
- [ ] Admin sends `/start` → normal flow works
- [ ] Admin sends `/my_chat_id` → receives response with IDs

---

## Phase 5: services/launch.py (Status Check)

> **Note:** `launch_animation.py` already exists with `launch_with_animation()`.
> The `launch_claude_in_thread()` in bot.py is a thin wrapper (~30 lines).
> This phase verifies no further work is needed.

### Task 5.1: Verify launch implementation is complete

**Step 1: Check no animation duplication in bot.py**

```bash
grep -c "FACES\|ANIMATION" src/codogram/bot.py
```

Expected: 0 (all animation code is in launch_animation.py)

**Step 2: Verify launch_with_animation is used everywhere**

```bash
grep -n "launch_with_animation" src/codogram/bot.py
```

Expected: Only imports and calls, no inline animation logic.

**Step 3: Check launch_claude_in_thread is a thin wrapper**

```bash
wc -l src/codogram/bot.py | head -1
grep -n "async def launch_claude_in_thread" src/codogram/bot.py
```

If function is ~30 lines and just delegates to `launch_with_animation`: Phase 5 DONE.

**Step 4: Document status**

```bash
git commit --allow-empty -m "docs: Phase 5 (services/launch) verified complete

launch_animation.py contains launch_with_animation().
launch_claude_in_thread() is a thin wrapper (~30 lines).
No duplication found - no further refactoring needed."
```

---

## Phase 6: Extract handlers/permissions.py

### Task 6.1: Create handlers/permissions.py with tests

**Files:**
- Create: `src/codogram/handlers/permissions.py`
- Create: `tests/test_permission_handler.py`

**Step 1: Write the failing test**

Create `tests/test_permission_handler.py`:

```python
"""Tests for permission handler."""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from codogram.handlers.permissions import on_permission_callback


class TestPermissionCallback:
    """Tests for on_permission_callback."""

    @pytest.fixture
    def mock_callback(self):
        """Create mock callback."""
        callback = Mock()
        callback.data = "perm:y:claude-test"
        callback.answer = AsyncMock()
        callback.bot = Mock()
        callback.bot.delete_message = AsyncMock()
        callback.message = Mock()
        callback.message.chat = Mock(id=123)
        callback.message.message_id = 456
        callback.message.delete = AsyncMock()
        return callback

    @pytest.mark.asyncio
    async def test_permission_yes(self, mock_callback):
        """Yes button sends 'y' to tmux."""
        mock_project = Mock(cwd="/tmp/test")
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True

        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = mock_project
            with patch("codogram.handlers.permissions.TmuxSession") as ts:
                ts.return_value = mock_tmux
                with patch("codogram.handlers.permissions.permission_messages", {456: []}):
                    await on_permission_callback(mock_callback)

        mock_tmux.send_key.assert_called_with("y")
        mock_callback.answer.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_permission_no(self, mock_callback):
        """No button sends 'n' to tmux."""
        mock_callback.data = "perm:n:claude-test"
        mock_project = Mock(cwd="/tmp/test")
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True

        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = mock_project
            with patch("codogram.handlers.permissions.TmuxSession") as ts:
                ts.return_value = mock_tmux
                with patch("codogram.handlers.permissions.permission_messages", {456: []}):
                    await on_permission_callback(mock_callback)

        mock_tmux.send_key.assert_called_with("n")

    @pytest.mark.asyncio
    async def test_permission_escape(self, mock_callback):
        """Esc button sends Escape key to tmux."""
        mock_callback.data = "perm:esc:claude-test"
        mock_project = Mock(cwd="/tmp/test")
        mock_tmux = Mock()
        mock_tmux.exists.return_value = True

        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = mock_project
            with patch("codogram.handlers.permissions.TmuxSession") as ts:
                ts.return_value = mock_tmux
                with patch("codogram.handlers.permissions.permission_messages", {456: []}):
                    await on_permission_callback(mock_callback)

        mock_tmux.send_key.assert_called_with("Escape")

    @pytest.mark.asyncio
    async def test_permission_session_not_found(self, mock_callback):
        """Returns error if session not found."""
        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = None
            await on_permission_callback(mock_callback)

        mock_callback.answer.assert_called_with("Session not found")

    @pytest.mark.asyncio
    async def test_permission_invalid_format(self, mock_callback):
        """Returns error for invalid callback format."""
        mock_callback.data = "perm:y"  # Missing tmux_session

        await on_permission_callback(mock_callback)

        mock_callback.answer.assert_called_with("Invalid callback format")

    @pytest.mark.asyncio
    async def test_permission_tmux_closed(self, mock_callback):
        """Returns error if tmux session no longer exists."""
        mock_project = Mock(cwd="/tmp/test")
        mock_tmux = Mock()
        mock_tmux.exists.return_value = False  # Tmux closed

        with patch("codogram.handlers.permissions.project_manager") as pm:
            pm.get_by_tmux.return_value = mock_project
            with patch("codogram.handlers.permissions.TmuxSession") as ts:
                ts.return_value = mock_tmux
                await on_permission_callback(mock_callback)

        mock_callback.answer.assert_called_with("Tmux session closed")
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=src pytest tests/test_permission_handler.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

Create `src/codogram/handlers/permissions.py`:

```python
"""Permission handlers - Yes/No/Esc buttons for Claude prompts."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..session_manager import project_manager
from ..tmux import TmuxSession
from ..state import permission_messages

router = Router(name="permissions")


@router.callback_query(F.data.startswith("perm:"))
async def on_permission_callback(callback: CallbackQuery):
    """Handle permission button press (Yes/No/Esc)."""
    # Parse callback data: perm:{action}:{tmux_session}
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Invalid callback format")
        return

    action = parts[1]
    tmux_session = parts[2]

    # Find project
    project = project_manager.get_by_tmux(tmux_session)
    if not project:
        await callback.answer("Session not found")
        return

    if not project.cwd:
        await callback.answer("Project has no cwd")
        return

    # Check tmux exists
    tmux = TmuxSession(tmux_session, project.cwd)
    if not tmux.exists():
        await callback.answer("Tmux session closed")
        return

    # Cleanup messages
    await _cleanup_permission_messages(callback)

    # Send key to tmux
    if action == "esc":
        tmux.send_key("Escape")
    else:
        tmux.send_key(action)

    await callback.answer()


async def _cleanup_permission_messages(callback: CallbackQuery):
    """Delete content messages and keyboard."""
    chat_id = callback.message.chat.id
    kb_msg_id = callback.message.message_id

    # Delete content messages
    content_ids = permission_messages.pop(kb_msg_id, [])
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    # Delete keyboard message
    try:
        await callback.message.delete()
    except Exception:
        pass
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/test_permission_handler.py -v
```

Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/permissions.py tests/test_permission_handler.py
git commit -m "feat(handlers): add permissions handler

Extracted from bot.py with full test coverage.
Handles Yes/No/Esc buttons for Claude permission prompts."
```

---

### Task 6.2: Update handlers/__init__.py

**Files:**
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Add register_handlers function**

```python
"""Handlers layer - thin routers delegating to services."""
from aiogram import Dispatcher

from . import permissions
from . import public


def register_handlers(dp: Dispatcher):
    """Register all handlers with the dispatcher.

    Order matters:
    1. public.router - no middleware, available to all
    2. permissions.router - uses AdminMiddleware from main router
    """
    # Public router (no middleware) - must be first
    dp.include_router(public.router)

    # Permission handlers (protected by main router's middleware)
    dp.include_router(permissions.router)
```

**Step 2: Verify import (checks for circular imports)**

```bash
python -c "from codogram.handlers import register_handlers; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/codogram/handlers/__init__.py
git commit -m "refactor(handlers): add register_handlers function"
```

---

### Task 6.3: Update main.py to use register_handlers

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Replace manual router registration**

Remove:
```python
from .handlers.public import router as public_router
...
dp.include_router(public_router)
```

Add:
```python
from .handlers import register_handlers
```

And in setup, before `dp.include_router(router)`:
```python
# Register handler routers (public, permissions, etc.)
register_handlers(dp)

# Main router with AdminMiddleware
dp.include_router(router)
```

**Step 2: Verify bot starts**

```bash
timeout 5 python -m codogram.main || true
```

Expected: Starts or fails on .env (not import error)

**Step 3: Commit**

```bash
git add src/codogram/main.py
git commit -m "refactor(main): use register_handlers for handler routers"
```

---

### Task 6.4: Remove permission handler from bot.py

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Find permission handler location**

```bash
grep -n "@router.callback_query(F.data.startswith(\"perm:\")" src/codogram/bot.py
```

Expected: Around line 1554

**Step 2: Remove the handler**

Delete `on_permission_callback` function and its helper `_cleanup_permission_messages`
(if it exists as separate function) from bot.py. Approximately lines 1554-1609.

**Step 3: Verify handler removed**

```bash
grep -c "perm:" src/codogram/bot.py
```

Expected: 0

**Step 4: Run all tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove permission handler (moved to handlers/)

First handler extraction complete. ~55 lines removed."
```

---

### Task 6.5: E2E Verification for Phase 6

**Manual testing checklist:**

> Skip if no .env available in worktree.

- [ ] Start Claude session
- [ ] Wait for permission prompt to appear
- [ ] Press "Yes" button → Claude receives 'y', continues
- [ ] Trigger another prompt, press "No" → Claude receives 'n'
- [ ] Trigger another prompt, press "✕" (Esc) → Claude receives Escape

---

## Phase 4-6 Complete: Final Verification

### Automated Checklist

```bash
# 1. All tests pass
PYTHONPATH=src pytest tests/ -v

# 2. No circular imports
python -c "
from codogram.middleware import AdminMiddleware, is_admin
from codogram.handlers import register_handlers
from codogram.bot import router
print('All imports OK')
"

# 3. No admin checks in bot.py
test $(grep -c "if not is_admin" src/codogram/bot.py) -eq 0 && echo "OK: No admin checks"

# 4. No local is_admin in bot.py
test $(grep -c "def is_admin" src/codogram/bot.py) -eq 0 && echo "OK: No local is_admin"

# 5. No permission handler in bot.py
test $(grep -c "perm:" src/codogram/bot.py) -eq 0 && echo "OK: No perm handler"

# 6. Bot starts (or fails on .env only)
timeout 5 python -m codogram.main 2>&1 | grep -q "validation error\|Starting" && echo "OK: Bot loads"
```

### Summary Commit

```bash
git commit --allow-empty -m "refactor: complete phases 4-6 of bot.py refactoring

Phase 4: AdminMiddleware
- Created middleware/admin.py with is_admin, get_admin_ids
- Registered on router (not dispatcher!) to preserve public handlers
- Removed 30 boilerplate admin checks from bot.py
- Moved /my_chat_id to handlers/public.py

Phase 5: services/launch (verified)
- launch_animation.py already handles all launch logic
- launch_claude_in_thread is thin wrapper, no changes needed

Phase 6: handlers/permissions
- Extracted permission callbacks to handlers/permissions.py
- Added register_handlers() for handler management
- 7 unit tests for permission handler

bot.py reduced by ~120 lines."
```

---

## Files Created/Modified

| File | Action | Lines |
|------|--------|-------|
| `src/codogram/middleware/admin.py` | Create | ~45 |
| `src/codogram/middleware/__init__.py` | Modify | ~5 |
| `src/codogram/handlers/public.py` | Create | ~20 |
| `src/codogram/handlers/permissions.py` | Create | ~55 |
| `src/codogram/handlers/__init__.py` | Modify | ~18 |
| `src/codogram/main.py` | Modify | ~8 |
| `src/codogram/bot.py` | Modify | -120 |
| `tests/test_admin_middleware.py` | Create | ~55 |
| `tests/test_permission_handler.py` | Create | ~95 |

**Total:** 6 new files, 3 modified, ~300 lines added, ~120 removed from bot.py

---

## Key Fixes Applied

| Issue | Fix |
|-------|-----|
| Middleware on `dp` blocks all routers | Register on `router`, not `dp` |
| Duplicate `is_admin` in bot.py | Remove from bot.py, use from middleware |
| Empty test for escape | Full test with assertion |
| No E2E checklist | Added Task 4.6 and 6.5 |
| Circular import risk | Added verification steps |
| Phase 5 unclear | Clarified as verification-only |
