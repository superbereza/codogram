# Фазы 4-6: Middleware, Launch, Permissions

## Архитектурное решение: Global AdminMiddleware

**Принцип:** Бот ТОЛЬКО для админов. Middleware на уровне Dispatcher защищает ВСЁ.

**Преимущества:**
- Одно место для проверки админа
- Все роутеры защищены автоматически
- При извлечении хендлеров не нужно думать о is_admin
- Не-админы получают свой ID автоматически (не нужна отдельная команда)

---

## Фаза 4: Вынести middleware/admin.py

**Цель:** Глобальная защита всех handlers + убрать повторяющиеся `if not is_admin()`

### Шаги

#### 4.0 Migrate keyboards.py → keyboards/

> Phase 1-3 skipped keyboards/ due to conflict with existing keyboards.py

```bash
mkdir -p src/codogram/keyboards
mv src/codogram/keyboards.py src/codogram/keyboards/permissions.py
```

```python
# keyboards/__init__.py
"""Keyboard builders for Telegram bot."""
from .permissions import permission_keyboard

__all__ = ["permission_keyboard"]
```

#### 4.1 middleware/admin.py

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

#### 4.2 Зарегистрировать на Dispatcher в main.py

```python
from .middleware.admin import AdminMiddleware

dp = Dispatcher()

# Global admin check - protects ALL routers
dp.message.middleware(AdminMiddleware())
dp.callback_query.middleware(AdminMiddleware())

# Include routers (all protected automatically)
dp.include_router(router)
```

**ВАЖНО:** Middleware на `dp`, не на `router`!
- `dp.message.middleware()` — защищает ВСЕ роутеры ✓
- `router.message.middleware()` — только этот роутер ✗

#### 4.3 Удалить проверки из bot.py

```python
# Было (в каждом handler):
@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    ...

# Стало:
@router.message(Command("start"))
async def cmd_start(message: Message):
    # Middleware уже проверил - сюда попадают только админы
    ...
```

#### 4.4 Переименовать /my_chat_id в /get_debug_ids

Команда остаётся только для админов (диагностика). Не-админы получают свой ID автоматически от middleware.

```python
@router.message(Command("get_debug_ids"))
async def cmd_get_debug_ids(message: Message):
    """Show debug IDs - admin only."""
    thread_id = message.message_thread_id
    thread_info = f"\nThread ID: `{thread_id}`" if thread_id else "\nThread ID: None (General)"
    await message.answer(
        f"Your user ID: `{message.from_user.id}`\n"
        f"This chat ID: `{message.chat.id}`{thread_info}",
        parse_mode="Markdown",
    )
```

### Тестирование

```python
# tests/test_admin_middleware.py
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
    async def test_non_admin_blocked_with_message(self):
        """Non-admin users are blocked and receive their ID."""
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
        """Non-admin callback gets show_alert popup."""
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

    def test_empty_admin_ids_blocks_everyone(self):
        """Empty ADMIN_IDS blocks all users."""
        with patch("codogram.middleware.admin.get_admin_ids", return_value=set()):
            assert is_admin(123) is False
            assert is_admin(0) is False
```

### Чеклист

- [ ] keyboards.py → keyboards/permissions.py
- [ ] AdminMiddleware создан с авто-показом ID
- [ ] Зарегистрирован на dp (не router!)
- [ ] Удалены все `if not is_admin()` из handlers (30 мест)
- [ ] /my_chat_id переименован в /get_debug_ids
- [ ] Не-админы получают свой ID автоматически
- [ ] Unit тесты зелёные (6 тестов)

### Definition of Done

- Middleware на dp защищает ВСЕ роутеры
- bot.py стал легче на ~60 строк
- Невозможно забыть admin check в новых handlers
- Не-админы получают понятное сообщение с ID

---

## Фаза 5: services/launch.py (Verification Only)

**Статус:** `launch_animation.py` уже существует с `launch_with_animation()`

**Цель:** Проверить, что дублирования нет

### Шаги

#### 5.1 Проверить отсутствие дублирования

```bash
# Нет animation констант в bot.py
grep -c "FACES\|ANIMATION" src/codogram/bot.py
# Expected: 0

# launch_with_animation используется
grep -n "launch_with_animation" src/codogram/bot.py
# Expected: только imports и вызовы
```

#### 5.2 Если дублирования нет

```bash
git commit --allow-empty -m "docs: Phase 5 (services/launch) verified complete

launch_animation.py contains launch_with_animation().
No duplication found - no further refactoring needed."
```

### Definition of Done

- Подтверждено: launch_animation.py содержит всю логику
- Дублирования в bot.py нет

---

## Фаза 6: Вынести handlers/permissions.py

**Цель:** Первый handler extraction — отработка паттерна

**Важно:** Middleware на dp уже защищает — не нужна проверка is_admin в хендлере!

### Шаги

#### 6.1 handlers/permissions.py

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

#### 6.2 handlers/__init__.py

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

#### 6.3 Обновить main.py

```python
from .handlers import register_handlers

# После middleware setup:
register_handlers(dp)

# Main bot router
dp.include_router(router)
```

### Тестирование

```python
# tests/test_permission_handler.py
import pytest
from unittest.mock import AsyncMock, Mock, patch

from codogram.handlers.permissions import on_permission_callback


class TestPermissionCallback:
    """Tests for on_permission_callback.

    Note: Admin check is done by middleware, not tested here.
    """

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

### Чеклист

- [ ] handlers/permissions.py создан
- [ ] Router зарегистрирован через register_handlers
- [ ] Удалён код из bot.py
- [ ] **Нет проверки is_admin** (middleware уже сделал)
- [ ] Unit тесты зелёные
- [ ] E2E: permission buttons работают

### Definition of Done

- Первый handler вынесен
- Паттерн отработан (middleware защищает всё)
- bot.py уменьшился на ~55 строк
