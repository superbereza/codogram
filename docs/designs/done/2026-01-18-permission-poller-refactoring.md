# Permission Poller Refactoring

**Date:** 2026-01-18
**Status:** Design

## Problem

`permission_poller.py` вырос до 502 строк с одной god-function `permission_poller()` на 400+ строк, которая делает 6 разных вещей:

1. Thinking status display (~85 строк)
2. Input suggestions (~50 строк)
3. Compact notification (~13 строк)
4. Crash detection (~13 строк)
5. Stuck message detection (~35 строк)
6. Permission prompt state machine (~200 строк)

Проблемы:
- Сложно читать и понимать
- Невозможно unit-тестировать отдельные части
- Сложно добавлять новые фичи

## Solution

Разбить на handler классы в отдельных файлах.

### File Structure

```
src/codogram/poller/
├── __init__.py          — re-export permission_poller, create_poller_task*
├── context.py           — PollerContext dataclass
├── base.py              — BaseHandler с helpers
├── handlers/
│   ├── __init__.py      — re-export all handlers
│   ├── compact.py       — CompactHandler
│   ├── thinking.py      — ThinkingHandler
│   ├── suggestions.py   — SuggestionsHandler
│   ├── stuck.py         — StuckHandler
│   └── permissions.py   — PermissionHandler
├── crash.py             — _detect_crash() function
└── poller.py            — permission_poller() main loop
```

Старый `permission_poller.py` удаляется.

### PollerContext

Shared context для всех handlers:

```python
@dataclass
class PollerContext:
    bot: Bot
    project: ProjectState
    thread: ThreadInfo | None
    tmux: TmuxSession
    queue: TelegramQueue
    chat_id: int
    thread_id: int | None
    log_prefix: str
```

### BaseHandler

Базовый класс с общим интерфейсом и helpers:

```python
class BaseHandler:
    def __init__(self, ctx: PollerContext):
        self.ctx = ctx

    async def process(self, screen: str) -> None:
        raise NotImplementedError

    # Helpers
    async def send(self, text: str, **kwargs) -> None:
        """Send message via queue."""
        ...

    async def send_with_key(self, text: str, key: str, **kwargs) -> None:
        """Send replaceable message."""
        ...

    async def edit_by_key(self, text: str, key: str) -> None:
        """Edit message by replace_key."""
        ...

    async def delete_by_key(self, key: str) -> None:
        """Delete message by replace_key."""
        ...
```

### Handlers

| Handler | Файл | Строк | Состояние | Описание |
|---------|------|-------|-----------|----------|
| CompactHandler | compact.py | ~20 | notified: bool | One-time compact notification |
| ThinkingHandler | thinking.py | ~50 | msg_key, last_update, last_text | Thinking status display |
| SuggestionsHandler | suggestions.py | ~40 | msg_key, last_suggestion | ReplyKeyboard suggestions |
| StuckHandler | stuck.py | ~35 | input_text, seen_count | Stuck message auto-Enter |
| PermissionHandler | permissions.py | ~150 | state, options, body, msg_ids | Permission prompt state machine |

### Main Loop

```python
async def permission_poller(
    bot: Bot,
    project: ProjectState,
    telegram_queue: TelegramQueue,
    thread: ThreadInfo | None = None,
) -> None:
    # Build context
    ctx = PollerContext(...)

    # Initialize handlers
    handlers = [
        CompactHandler(ctx),
        ThinkingHandler(ctx),
        SuggestionsHandler(ctx),
        StuckHandler(ctx),
        PermissionHandler(ctx),
    ]

    # Main loop
    while True:
        await asyncio.sleep(settings.permission_poller_interval)

        try:
            screen = ctx.tmux.capture_pane()
        except Exception as e:
            logger.warning(f"{ctx.log_prefix}: capture error: {e}")
            continue

        # Crash detection (inline — stateless, exits poller)
        if crash := _detect_crash(screen):
            await notify_crash(ctx, crash)
            return

        # Process all handlers
        for handler in handlers:
            try:
                await handler.process(screen)
            except Exception as e:
                logger.warning(f"{ctx.log_prefix}: {handler.__class__.__name__} error: {e}")
```

### Imports

Внешний код не меняется благодаря re-export:

```python
# Было:
from .permission_poller import create_poller_task_for_thread

# Станет:
from .poller import create_poller_task_for_thread
```

## Testing

Unit тесты для каждого handler:

```python
def test_compact_handler_notifies_once():
    ctx = make_test_context()
    handler = CompactHandler(ctx)

    await handler.process("✻ Compacting conversation…")
    assert len(ctx.queue.sent) == 1

    await handler.process("✻ Compacting conversation…")
    assert len(ctx.queue.sent) == 1  # No duplicate

def test_stuck_handler_sends_enter_after_debounce():
    ctx = make_test_context()
    ctx.thread.last_sent_message = "hello"
    handler = StuckHandler(ctx)

    await handler.process("❯ hello")
    assert ctx.tmux.keys_sent == []

    await handler.process("❯ hello")
    assert ctx.tmux.keys_sent == ["Enter"]
```

## Migration

1. Создать `src/codogram/poller/` структуру
2. Перенести код по файлам
3. Обновить imports в остальном коде
4. Удалить `permission_poller.py`
5. Запустить тесты

## Result

- **Читаемость:** каждый handler — отдельный файл 20-150 строк
- **Тестируемость:** unit тесты на изолированные handlers
- **Расширяемость:** новый handler = новый файл + добавить в список
