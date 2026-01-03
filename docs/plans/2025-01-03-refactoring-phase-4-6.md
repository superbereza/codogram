# Bot.py Refactoring: Phases 4-6 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract AdminMiddleware (global protection), verify launch logic, and create first handler module (permissions).

**Architecture:** Global middleware on Dispatcher protects ALL routers. Handlers are thin routers delegating to services.

**Tech Stack:** Python 3.11+, aiogram 3.x middleware, pytest

**Design Doc:** `docs/designs/2025-12-27-bot-refactoring/02-phase-4-6.md`

**Key Decision:** Middleware on `dp` (not `router`) — protects everything, no need for is_admin checks in handlers.

**Current State:**
- `launch_animation.py` already exists with `launch_with_animation()`
- 30 admin checks (`if not is_admin(...)`) scattered in bot.py
- `is_admin()` and `get_admin_ids()` defined in bot.py (lines 42-51)

---

## Phase 4: Extract middleware/admin.py (Global Protection)

### Task 4.0: Migrate keyboards.py to keyboards/ directory

> **Background:** Phase 1-3 skipped keyboards/ creation due to conflict with existing keyboards.py.
> Now we migrate it to proper structure.

**Files:**
- Move: `src/codogram/keyboards.py` → `src/codogram/keyboards/permissions.py`
- Create: `src/codogram/keyboards/__init__.py`

**Step 1: Create keyboards directory and move file**

```bash
mkdir -p src/codogram/keyboards
mv src/codogram/keyboards.py src/codogram/keyboards/permissions.py
```

**Step 2: Create keyboards/__init__.py with re-export**

```python
"""Keyboard builders for Telegram bot."""
from .permissions import permission_keyboard

__all__ = ["permission_keyboard"]
```

**Step 3: Verify imports still work**

```bash
python -c "from codogram.keyboards import permission_keyboard; print('OK')"
```

Expected: `OK` (existing imports `from .keyboards import permission_keyboard` still work)

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/codogram/keyboards/
git commit -m "refactor: migrate keyboards.py to keyboards/ directory

Prepares for additional keyboard modules (start_flow, etc.)"
```

---

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
    async def test_non_admin_message_blocked_with_id(self):
        """Non-admin Message users are blocked and receive their ID."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock()
        event.reply = AsyncMock()
        data = {"event_from_user": Mock(id=999)}

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None
        event.reply.assert_called_once()
        # Check message contains user ID
        call_args = event.reply.call_args[0][0]
        assert "999" in call_args

    @pytest.mark.asyncio
    async def test_non_admin_callback_gets_alert(self):
        """Non-admin CallbackQuery gets show_alert popup with ID."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock(spec=['answer'])  # CallbackQuery-like
        event.answer = AsyncMock()
        data = {"event_from_user": Mock(id=999)}

        with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
            result = await middleware(handler, event, data)

        handler.assert_not_called()
        event.answer.assert_called_once()
        assert event.answer.call_args[1].get('show_alert') is True
        # Check ID is in message
        call_args = event.answer.call_args[0][0]
        assert "999" in call_args

    @pytest.mark.asyncio
    async def test_no_user_blocked_silently(self):
        """Events without user are blocked silently."""
        middleware = AdminMiddleware()
        handler = AsyncMock()
        event = Mock()
        data = {}  # No event_from_user

        result = await middleware(handler, event, data)

        handler.assert_not_called()
        assert result is None

    def test_empty_admin_ids_blocks_everyone(self):
        """Empty ADMIN_IDS blocks all users."""
        with patch("codogram.middleware.admin.get_admin_ids", return_value=set()):
            assert is_admin(123) is False
            assert is_admin(0) is False
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=src pytest tests/test_admin_middleware.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

Create `src/codogram/middleware/admin.py`:

```python
"""Admin middleware - global protection for all handlers."""
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
    """Block non-admins globally. Shows their ID automatically.

    Register on Dispatcher level (protects ALL routers):
        dp.message.middleware(AdminMiddleware())
        dp.callback_query.middleware(AdminMiddleware())

    Non-admins receive their ID automatically - no /my_chat_id needed.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        if user is None:
            return None

        if is_admin(user.id):
            return await handler(event, data)

        # Non-admin: show helpful message with their ID
        await self._reject_non_admin(event, user.id)
        return None

    async def _reject_non_admin(self, event: TelegramObject, user_id: int):
        """Send rejection message with user's ID."""
        message = (
            f"Вы не админ.\n"
            f"Ваш ID: `{user_id}`\n"
            f"Попросите добавить в ADMIN_IDS"
        )

        if hasattr(event, 'answer'):
            # CallbackQuery - popup
            await event.answer(
                f"Вы не админ. Ваш ID: {user_id}",
                show_alert=True
            )
        elif hasattr(event, 'reply'):
            # Message
            await event.reply(message, parse_mode="Markdown")
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=src pytest tests/test_admin_middleware.py -v
```

Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/codogram/middleware/admin.py tests/test_admin_middleware.py
git commit -m "feat(middleware): add global AdminMiddleware

Blocks non-admins with helpful message showing their ID.
Register on Dispatcher level to protect ALL routers."
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

### Task 4.3: Register middleware on DISPATCHER in main.py

**Files:**
- Modify: `src/codogram/main.py`

> **CRITICAL:** Middleware on `dp`, not `router`!
> - `dp.message.middleware()` — protects ALL routers ✓
> - `router.message.middleware()` — only that router ✗

**Step 1: Add middleware import and registration**

Add import at top:
```python
from .middleware.admin import AdminMiddleware
```

After `dp = Dispatcher()`, add:
```python
# Global admin check - protects ALL routers
dp.message.middleware(AdminMiddleware())
dp.callback_query.middleware(AdminMiddleware())
```

**Step 2: Verify no circular imports**

```bash
python -c "from codogram.main import main; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/codogram/main.py
git commit -m "refactor(main): register AdminMiddleware on Dispatcher

IMPORTANT: Middleware on dp level protects ALL routers globally.
Non-admins receive their ID automatically."
```

---

### Task 4.4: Remove admin checks AND is_admin function from bot.py

**Files:**
- Modify: `src/codogram/bot.py`

> **Scope:** Exactly 30 admin checks to remove.

**Step 1: List all admin check locations**

```bash
grep -n "if not is_admin" src/codogram/bot.py | cut -d: -f1 | tr '\n' ' '
```

Expected: 30 line numbers.

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

**Step 3: Remove is_admin and get_admin_ids from bot.py**

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

**Step 4: Verify cleanup complete**

```bash
# No admin checks remaining
grep -c "if not is_admin" src/codogram/bot.py
# Expected: 0

# No local is_admin function
grep -c "def is_admin" src/codogram/bot.py
# Expected: 0
```

**Step 5: Run tests**

```bash
PYTHONPATH=src pytest tests/ -v --tb=short
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove admin checks and is_admin function

- Removed ~30 'if not is_admin()' blocks (middleware handles this)
- Removed is_admin/get_admin_ids (moved to middleware/admin.py)
- All handlers now protected by global AdminMiddleware"
```

---

### Task 4.5: Rename /my_chat_id to /get_debug_ids

**Files:**
- Modify: `src/codogram/bot.py`
- Modify: `src/codogram/main.py` (bot commands list)

**Step 1: Find and rename handler in bot.py**

```bash
grep -n "my_chat_id" src/codogram/bot.py
```

Change handler from:
```python
@router.message(Command("my_chat_id"))
async def cmd_my_chat_id(message: Message):
```

To:
```python
@router.message(Command("get_debug_ids"))
async def cmd_get_debug_ids(message: Message):
    """Show debug IDs - admin only (protected by middleware)."""
```

**Step 2: Update bot commands in main.py**

Find `BotCommand(command="my_chat_id"` and change to:
```python
BotCommand(command="get_debug_ids", description="Show debug IDs (admin only)"),
```

**Step 3: Verify**

```bash
grep "my_chat_id" src/codogram/bot.py src/codogram/main.py
# Expected: nothing (all renamed)

grep "get_debug_ids" src/codogram/bot.py src/codogram/main.py
# Expected: 2 matches (handler + command)
```

**Step 4: Commit**

```bash
git add src/codogram/bot.py src/codogram/main.py
git commit -m "refactor: rename /my_chat_id to /get_debug_ids

Now admin-only (middleware protects). Non-admins get their ID
automatically from middleware rejection message."
```

---

### Task 4.6: E2E Verification for Phase 4

**Manual testing checklist:**

> Skip if no .env available in worktree. These tests require running bot.

- [ ] Non-admin sends any message → receives "Вы не админ. Ваш ID: ..."
- [ ] Non-admin presses any button → receives popup with ID
- [ ] Admin sends `/start` → normal flow works
- [ ] Admin sends `/get_debug_ids` → receives debug info

---

## Phase 5: services/launch.py (Status Check)

> **Note:** `launch_animation.py` already exists with `launch_with_animation()`.
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

> **Important:** Middleware on dp already protects ALL routers.
> No need for is_admin check in handlers!

### Task 6.1: Create handlers/permissions.py with tests

**Files:**
- Create: `src/codogram/handlers/permissions.py`
- Create: `tests/test_permission_handler.py`

**Step 1: Write the failing test**

Create `tests/test_permission_handler.py`:

```python
"""Tests for permission handler.

Note: Admin check is done by global middleware, not tested here.
"""
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
    """Handle permission button press (Yes/No/Esc).

    Note: Admin check done by global AdminMiddleware on dp level.
    """
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

Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/permissions.py tests/test_permission_handler.py
git commit -m "feat(handlers): add permissions handler

Extracted from bot.py with full test coverage.
Handles Yes/No/Esc buttons for Claude permission prompts.
Admin check handled by global middleware."
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


def register_handlers(dp: Dispatcher):
    """Register all handler routers.

    Note: All routers are protected by AdminMiddleware on dp level.
    No need to add middleware to individual routers.
    """
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

**Step 1: Add handler registration**

Add import:
```python
from .handlers import register_handlers
```

After middleware setup, before `dp.include_router(router)`:
```python
# Register handler routers (all protected by AdminMiddleware)
register_handlers(dp)

# Main router
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
grep -c "@router.callback_query.*perm:" src/codogram/bot.py
```

Expected: 0 (handler removed; keyboard builder is in keyboards.py, not bot.py)

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
test $(grep -c "@router.callback_query.*perm:" src/codogram/bot.py) -eq 0 && echo "OK: No perm handler"

# 6. Command renamed
grep -q "get_debug_ids" src/codogram/bot.py && echo "OK: Command renamed"

# 7. Bot starts (or fails on .env only)
timeout 5 python -m codogram.main 2>&1 | grep -q "validation error\|Starting" && echo "OK: Bot loads"
```

### Summary Commit

```bash
git commit --allow-empty -m "refactor: complete phases 4-6 of bot.py refactoring

Phase 4: Global AdminMiddleware
- Created middleware/admin.py with is_admin, get_admin_ids
- Registered on DISPATCHER (not router!) - protects ALL routers
- Non-admins receive their ID automatically
- Removed 30 boilerplate admin checks from bot.py
- Renamed /my_chat_id to /get_debug_ids (admin only)

Phase 5: services/launch (verified)
- launch_animation.py already handles all launch logic
- launch_claude_in_thread is thin wrapper, no changes needed

Phase 6: handlers/permissions
- Extracted permission callbacks to handlers/permissions.py
- Added register_handlers() for handler management
- NO is_admin checks needed (middleware protects all)
- 6 unit tests for permission handler

bot.py reduced by ~120 lines."
```

---

## Files Created/Modified

| File | Action | Lines |
|------|--------|-------|
| `src/codogram/keyboards/permissions.py` | Move from keyboards.py | ~40 |
| `src/codogram/keyboards/__init__.py` | Create | ~5 |
| `src/codogram/middleware/admin.py` | Create | ~60 |
| `src/codogram/middleware/__init__.py` | Modify | ~5 |
| `src/codogram/handlers/permissions.py` | Create | ~55 |
| `src/codogram/handlers/__init__.py` | Modify | ~12 |
| `src/codogram/main.py` | Modify | ~10 |
| `src/codogram/bot.py` | Modify | -120 |
| `tests/test_admin_middleware.py` | Create | ~70 |
| `tests/test_permission_handler.py` | Create | ~85 |

**Total:** 6 new files, 4 modified, ~340 lines added, ~120 removed from bot.py

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Middleware on `dp` (not `router`) | Protects ALL routers globally, no inheritance issues |
| Non-admins get ID automatically | No need for /my_chat_id public command |
| /my_chat_id → /get_debug_ids | Admin-only debug command |
| No is_admin in handlers | Middleware already checked - DRY |
| No handlers/public.py | All handlers protected by default |
