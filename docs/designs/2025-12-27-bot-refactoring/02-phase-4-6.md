# Фазы 4-6: Middleware, Launch, Permissions

## Фаза 4: Вынести middleware/admin.py

**Цель:** Убрать повторяющиеся `if not is_admin()` из каждого handler

### Шаги

#### 4.1 middleware/admin.py

```python
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from typing import Callable, Any, Awaitable

from ..config import settings

_admin_ids: set[int] | None = None

def get_admin_ids() -> set[int]:
    global _admin_ids
    if _admin_ids is None:
        _admin_ids = settings.get_admin_ids()
    return _admin_ids

def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()

class AdminMiddleware(BaseMiddleware):
    """Skip handlers for non-admin users."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")

        if user is None or not is_admin(user.id):
            return  # Silently ignore non-admins

        return await handler(event, data)
```

#### 4.2 Зарегистрировать в main.py

```python
from .middleware.admin import AdminMiddleware

# В setup:
dp.message.middleware(AdminMiddleware())
dp.callback_query.middleware(AdminMiddleware())
```

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
    # Middleware уже проверил
    ...
```

#### 4.4 Особый случай: /my_chat_id

```python
# handlers/public.py — handlers без admin check
public_router = Router()  # Без AdminMiddleware

@public_router.message(Command("my_chat_id"))
async def cmd_my_chat_id(message: Message):
    await message.answer(
        f"Your user ID: `{message.from_user.id}`",
        parse_mode="Markdown"
    )
```

### Тестирование

```python
# tests/test_admin_middleware.py
import pytest
from unittest.mock import AsyncMock, Mock, patch

from codogram.middleware.admin import AdminMiddleware

@pytest.mark.asyncio
async def test_admin_allowed():
    middleware = AdminMiddleware()
    handler = AsyncMock()
    event = Mock()
    data = {"event_from_user": Mock(id=123)}

    with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
        await middleware(handler, event, data)

    handler.assert_called_once()

@pytest.mark.asyncio
async def test_non_admin_blocked():
    middleware = AdminMiddleware()
    handler = AsyncMock()
    event = Mock()
    data = {"event_from_user": Mock(id=999)}

    with patch("codogram.middleware.admin.get_admin_ids", return_value={123}):
        await middleware(handler, event, data)

    handler.assert_not_called()
```

### Чеклист

- [ ] AdminMiddleware создан
- [ ] Зарегистрирован в main.py
- [ ] Удалены все `if not is_admin()` из handlers (~15-20 мест)
- [ ] `/my_chat_id` работает для всех
- [ ] Остальные команды работают только для админов
- [ ] Unit тесты зелёные

### Definition of Done

- Middleware работает
- bot.py стал легче на ~40 строк
- Невозможно забыть admin check в новых handlers

---

## Фаза 5: Вынести services/launch.py

**Цель:** Объединить дублированную логику запуска Claude

### Анализ дублей

```
launch_claude_new()       # строки 336-448 (113 строк)
launch_claude_in_thread() # строки 451-568 (118 строк)

Общее:
- Animation faces (40 строк) — идентичны
- Wait loop (is_claude_ready) — идентичен
- Status message edit — идентичен

Различия:
- tmux session naming
- Куда отправлять сообщения (chat vs thread)
- project.awaiting_new_session vs thread.awaiting_new_session
```

### Шаги

#### 5.1 services/launch.py

```python
import asyncio
from dataclasses import dataclass

from aiogram import Bot

from ..adapters.tmux import TmuxAdapter
from ..domain.models import ProjectState, ThreadInfo
from ..project_launcher import create_tmux_with_claude, is_tmux_session_exists

ANIMATION_FACES = [
    "[._.]", "[._.]", "[-_-]", "[-_-]", "[.o.]", "[o_o]",
    "[o_o]", "[◉_◉]", "[◉_◉]", "[◉_◉]",
    "[◉︿◉]", "[◉~◉]", "[°_°]", "[°_°]",
    "[°□°]", "[°□°]",
    "[ಠ_ಠ]", "[ಠ_ಠ]", "[ಠ︿ಠ]", "[ಠ益ಠ]",
    "[>_<]", "[>︿<]", "[>△<]",
    "[×_×]", "[×_×]", "[✖_✖]", "[✖益✖]",
    "[☠_☠]", "[☠_☠]",
    "[._.]",
]

@dataclass
class LaunchResult:
    success: bool
    tmux_session: str | None = None
    error: str | None = None

class LaunchService:
    def __init__(self, project_manager, telegram_adapter):
        self.project_manager = project_manager
        self.telegram = telegram_adapter

    async def launch_claude(
        self,
        bot: Bot,
        chat_id: int,
        project: ProjectState,
        thread: ThreadInfo | None = None,
        message_thread_id: int | None = None,
    ) -> LaunchResult:
        """Launch Claude for project or thread."""

        # Determine tmux session name
        if thread:
            tmux_name = thread.get_tmux_session(project.project_name)
            thread.awaiting_new_session = True
        else:
            tmux_name = f"claude-{project.project_name}"
            project.awaiting_new_session = True

        # Initial delay
        await asyncio.sleep(3.0)

        # Create or reuse tmux
        result = await self._ensure_tmux(project, tmux_name, thread)
        if not result.success:
            return result

        # Show animation
        await self._show_animation(
            bot, chat_id, tmux_name, project.cwd, message_thread_id
        )

        # Start tasks
        await self._start_tasks(project, thread)

        return LaunchResult(success=True, tmux_session=tmux_name)

    async def _ensure_tmux(
        self,
        project: ProjectState,
        tmux_name: str,
        thread: ThreadInfo | None,
    ) -> LaunchResult:
        """Create or reuse tmux session."""
        import subprocess

        convention = f"claude-{project.project_name}"

        # Case 1: Our tmux exists - reuse
        if project.tmux_session == convention and is_tmux_session_exists(convention):
            subprocess.run(
                ["tmux", "send-keys", "-t", convention, "claude", "Enter"],
                capture_output=True,
            )
            return LaunchResult(success=True, tmux_session=convention)

        # Case 2: Create new tmux
        result = create_tmux_with_claude(tmux_name, project.cwd)
        if not result.success:
            return LaunchResult(success=False, error=result.error)

        if not thread:
            project.tmux_session = tmux_name

        return LaunchResult(success=True, tmux_session=tmux_name)

    async def _show_animation(
        self,
        bot: Bot,
        chat_id: int,
        tmux_name: str,
        cwd: str,
        message_thread_id: int | None,
    ):
        """Show doom-guy animation while waiting for Claude."""
        tmux = TmuxAdapter(tmux_name, cwd)

        status_msg = await bot.send_message(
            chat_id,
            "`[._.]`",
            parse_mode="Markdown",
            message_thread_id=message_thread_id,
        )

        frame = 0
        for _ in range(60):  # max 60 seconds
            if tmux.is_claude_ready():
                break
            face = ANIMATION_FACES[frame % len(ANIMATION_FACES)]
            try:
                await status_msg.edit_text(f"`{face}`", parse_mode="Markdown")
            except Exception:
                pass
            await asyncio.sleep(1.5)
            frame += 1

        # Happy face when ready
        try:
            await status_msg.edit_text("`[≖‿≖] Ready!`", parse_mode="Markdown")
            await asyncio.sleep(1.0)
            await status_msg.delete()
        except Exception:
            pass

    async def _start_tasks(self, project: ProjectState, thread: ThreadInfo | None):
        """Start poller and watcher tasks."""
        # Implementation depends on how task starters are injected
        pass
```

#### 5.2 Обновить bot.py

```python
# Было:
await launch_claude_new(callback.message, project, start_poller, start_watcher)

# Стало:
result = await launch_service.launch_claude(
    bot=callback.bot,
    chat_id=callback.message.chat.id,
    project=project,
)
if not result.success:
    await callback.message.edit_text(f"Ошибка: {result.error}")
```

### Тестирование

```python
# tests/test_launch_service.py
import pytest
from unittest.mock import AsyncMock, Mock

from codogram.services.launch import LaunchService, ANIMATION_FACES

def test_animation_faces_not_empty():
    assert len(ANIMATION_FACES) > 0
    assert ANIMATION_FACES[0] == "[._.]"

@pytest.mark.asyncio
async def test_launch_creates_tmux(mock_tmux, mock_bot):
    service = LaunchService(Mock(), Mock())
    project = Mock(
        project_name="test",
        cwd="/tmp/test",
        tmux_session=None,
    )

    with patch("codogram.services.launch.create_tmux_with_claude") as mock_create:
        mock_create.return_value = Mock(success=True)
        result = await service.launch_claude(mock_bot, 123, project)

    assert result.success
    assert result.tmux_session == "claude-test"

@pytest.mark.asyncio
async def test_launch_thread_uses_thread_tmux_name():
    service = LaunchService(Mock(), Mock())
    project = Mock(project_name="test", cwd="/tmp/test")
    thread = Mock(
        get_tmux_session=lambda name: f"claude-{name}-mystic",
        awaiting_new_session=False,
    )

    with patch("codogram.services.launch.create_tmux_with_claude") as mock_create:
        mock_create.return_value = Mock(success=True)
        result = await service.launch_claude(Mock(), 123, project, thread=thread)

    assert result.tmux_session == "claude-test-mystic"
```

### Чеклист

- [ ] LaunchService создан
- [ ] Анимация вынесена в константу (один раз)
- [ ] launch_claude() работает для project
- [ ] launch_claude() работает для thread
- [ ] Старые функции удалены из bot.py
- [ ] Unit тесты зелёные
- [ ] E2E: `/start` запускает Claude с анимацией

### Definition of Done

- Дублирование устранено (~150 строк сэкономлено)
- LaunchService покрыт тестами
- bot.py уменьшился на ~230 строк

---

## Фаза 6: Вынести handlers/permissions.py

**Цель:** Первый тонкий handler — простой случай для отработки паттерна

### Шаги

#### 6.1 handlers/permissions.py

```python
from aiogram import Router, F
from aiogram.types import CallbackQuery

from ..session_manager import project_manager
from ..adapters.tmux import TmuxAdapter
from ..state import permission_messages
from ..logging_config import logger

router = Router()

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

    # Check tmux exists
    tmux = TmuxAdapter(tmux_session, project.cwd or "/tmp")
    if not tmux.exists():
        await callback.answer("Tmux session closed")
        return

    # Cleanup messages
    await _cleanup_permission_messages(callback)

    # Send key
    if action == "esc":
        tmux.send_key("Escape")
    else:
        tmux.send_key(action)

    await callback.answer()

async def _cleanup_permission_messages(callback: CallbackQuery):
    """Delete content messages and keyboard."""
    chat_id = callback.message.chat.id
    kb_msg_id = callback.message.message_id

    content_ids = permission_messages.pop(kb_msg_id, [])
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    try:
        await callback.message.delete()
    except Exception:
        pass
```

#### 6.2 handlers/__init__.py

```python
from aiogram import Dispatcher
from . import permissions

def register_handlers(dp: Dispatcher):
    dp.include_router(permissions.router)
```

#### 6.3 Обновить main.py

```python
from .handlers import register_handlers

# В setup:
register_handlers(dp)
```

### Тестирование

```python
# tests/test_permission_handler.py
import pytest
from unittest.mock import AsyncMock, Mock, patch

@pytest.mark.asyncio
async def test_permission_yes():
    callback = Mock(
        data="perm:y:claude-test",
        answer=AsyncMock(),
        message=Mock(
            chat=Mock(id=123),
            message_id=456,
            delete=AsyncMock(),
        ),
        bot=Mock(delete_message=AsyncMock()),
    )

    with patch("codogram.handlers.permissions.project_manager") as mock_pm:
        mock_pm.get_by_tmux.return_value = Mock(cwd="/tmp")
        with patch("codogram.handlers.permissions.TmuxAdapter") as mock_tmux:
            mock_tmux.return_value.exists.return_value = True
            await on_permission_callback(callback)

    mock_tmux.return_value.send_key.assert_called_with("y")

@pytest.mark.asyncio
async def test_permission_escape():
    # Similar to above but with action="esc"
    # Should call send_key("Escape")
    pass

@pytest.mark.asyncio
async def test_permission_invalid_session():
    callback = Mock(data="perm:y:nonexistent", answer=AsyncMock())

    with patch("codogram.handlers.permissions.project_manager") as mock_pm:
        mock_pm.get_by_tmux.return_value = None
        await on_permission_callback(callback)

    callback.answer.assert_called_with("Session not found")
```

### E2E тест

- [ ] Запустить Claude
- [ ] Дождаться permission prompt
- [ ] Нажать Yes в Telegram
- [ ] Claude получает "y" и продолжает

### Чеклист

- [ ] handlers/permissions.py создан
- [ ] Router зарегистрирован
- [ ] Удалён код из bot.py
- [ ] Unit тесты зелёные
- [ ] E2E: permission buttons работают

### Definition of Done

- Первый handler вынесен
- Паттерн отработан
- bot.py уменьшился на ~50 строк
