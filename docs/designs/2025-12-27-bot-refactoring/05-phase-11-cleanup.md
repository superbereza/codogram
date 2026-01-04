# Phase 11: Финализация и Техдолг

> **Статус:** Черновик 2025-01-04
>
> **Предыдущая фаза:** Phase 10 завершена — bot.py удалён (522 строки → 0)

## Цель

Устранить технический долг, накопившийся за время рефакторинга:
- Удалить dead code
- Унифицировать дублирующийся код
- Вынести hardcoded значения в config
- Исправить архитектурные костыли

**Ожидаемая экономия:** ~350-400 строк кода

---

## 1. CRITICAL: Унификация permission_poller.py

### Проблема

Две почти идентичные функции по ~180 строк каждая:
- `permission_poller_for_project()` (lines 75-264)
- `permission_poller_for_thread()` (lines 271-451)

Отличия только в:
- `thread_id`: None vs thread.thread_id
- `tmux_name`: project.tmux_session vs thread.get_tmux_session()
- Логирование: "Poller" vs "Thread poller"

### Решение

Унифицировать в одну функцию с параметром `thread: ThreadInfo | None`:

```python
async def permission_poller(
    bot: Bot,
    project: ProjectState,
    telegram_queue: "TelegramQueue",
    thread: ThreadInfo | None = None,  # None = project-level
) -> None:
    """Unified permission poller for project or thread."""
    # Determine context
    chat_id = project.chat_id
    thread_id = thread.thread_id if thread else None
    tmux_name = (thread.get_tmux_session(project.project_name)
                 if thread else project.tmux_session)
    auto_accept = thread.auto_accept if thread else project.auto_accept
    log_prefix = f"Thread poller [{thread.name}]" if thread else "Poller"

    # ... shared state machine logic
```

### Файлы для обновления

| Файл | Изменение |
|------|-----------|
| `permission_poller.py` | Удалить дубль, оставить одну функцию |
| `launch_animation.py:54-57` | Обновить вызов |
| `session_manager.py:383-385` | Обновить вызов |

**Экономия:** ~100 строк

---

## 2. Dead Code: Удаление неиспользуемого кода

### 2.1 find_missed_entries()

**Файл:** `watcher.py:28-50` (23 строки)

**Статус:** Функция определена, но нигде не вызывается.

**Действие:** Удалить функцию.

### 2.2 _maybe_start_tasks()

**Файл:** `session_manager.py:323-326`

**Статус:** Deprecated, показывает warning при вызове:
```python
async def _maybe_start_tasks(...):
    """DEPRECATED: Tasks are now started per-thread..."""
    logger.warning("_maybe_start_tasks called but is deprecated...")
```

**Действие:** Удалить метод и вызов на строке 319.

### 2.3 Deprecated поля в ProjectState

**Файл:** `session_manager.py:133-145`

8 полей, дублирующих функционал threads:
```python
session_id: str | None = None              # → threads[None].session_id
jsonl_path: str | None = None              # → threads[None].jsonl_path
watcher_task: asyncio.Task | None = None   # → threads[None].watcher_task
tmux_session: str | None = None            # → threads[None].get_tmux_session()
poller_task: asyncio.Task | None = None    # → threads[None].poller_task
last_sent_message: str | None = None       # → threads[None].last_sent_message
binding_task: asyncio.Task | None = None   # → threads[None].binding_task
awaiting_new_session: bool = False         # → threads[None].awaiting_new_session
```

**Действие:**
1. Найти все места использования (grep)
2. Мигрировать на threads[None]
3. Удалить поля

**Риск:** Нужна миграция старых .config.json файлов.

**Экономия:** ~50 строк условной логики

---

## 3. Hardcoded → config.py

### Текущие константы

| Файл | Строка | Константа | Значение |
|------|--------|-----------|----------|
| `permission_poller.py` | 95, 291 | `DEBOUNCE_TIME` | 0.5 |
| `permission_poller.py` | 96, 292 | `POLL_INTERVAL` | 0.5 |
| `history_watcher.py` | 16 | `REFRESH_INTERVAL` | 15 |
| `history_watcher.py` | 238 | `BINDING_TIMEOUT` | 300 |
| `history_watcher.py` | 239 | `BINDING_INTERVAL` | 0.5 |
| `launch_animation.py` | 104 | (implicit) | 120 |
| `session_manager.py` | 79 | (implicit) | 30 |
| `watcher.py` | 139, 172 | `poll_interval` | 0.5 |

### Решение

Добавить в `config.py`:

```python
class Settings(BaseSettings):
    # ... existing ...

    # Timing constants
    permission_poller_debounce: float = 0.5
    permission_poller_interval: float = 0.5
    history_watcher_interval: int = 15
    session_binding_timeout: int = 300
    session_binding_interval: float = 0.5
    jsonl_watcher_interval: float = 0.5
    claude_launch_timeout: int = 120
    project_cleanup_days: int = 30
```

### Использование

```python
from .config import settings

# Вместо:
DEBOUNCE_TIME = 0.5

# Теперь:
settings.permission_poller_debounce
```

---

## 4. Архитектурные костыли

### 4.1 sys.modules hack в main.py

**Файл:** `main.py:4-7`

```python
import sys
if __name__ == '__main__':
    sys.modules['codogram.main'] = sys.modules['__main__']
```

**Проблема:** Workaround для circular imports. Используется в:
- `handlers/messages.py:93`: `from .. import main`
- `handlers/start.py:173`: `from ..main import telegram_queue`

**Решение:** DI через middleware:

```python
# middleware/dependencies.py
class DependencyMiddleware(BaseMiddleware):
    def __init__(self, telegram_queue: TelegramQueue):
        self.telegram_queue = telegram_queue

    async def __call__(self, handler, event, data):
        data['telegram_queue'] = self.telegram_queue
        return await handler(event, data)

# main.py
dp.message.middleware(DependencyMiddleware(telegram_queue))

# handlers/messages.py
async def on_message(message: Message, telegram_queue: TelegramQueue):
    # Inject через middleware
```

### 4.2 time.sleep() в tmux.py

**Файл:** `tmux.py:45, 56, 67`

```python
def send(self, text: str) -> None:
    # ...
    time.sleep(0.05)  # Блокирует event loop!
    time.sleep(0.1)
    time.sleep(0.2)
```

**Проблема:** Блокирующие вызовы в async контексте.

**Решение:** Async wrapper:

```python
# adapters/tmux_async.py
class TmuxSessionAsync:
    def __init__(self, name: str, cwd: str):
        self._sync = TmuxSession(name, cwd)

    async def send(self, text: str) -> None:
        """Non-blocking send with asyncio.sleep."""
        # Run subprocess in executor
        await asyncio.get_event_loop().run_in_executor(
            None, self._send_keys, text
        )
        await asyncio.sleep(0.05)
        # ...
```

### 4.3 mkdir при импорте tmux.py

**Файл:** `tmux.py:10-11`

```python
TMUX_DIR = Path.home() / ".tmux-claude"
TMUX_DIR.mkdir(exist_ok=True)  # Выполняется при импорте!
```

**Решение:** Lazy initialization:

```python
class TmuxSession:
    _dir_created = False

    @classmethod
    def _ensure_dir(cls):
        if not cls._dir_created:
            TMUX_DIR.mkdir(exist_ok=True)
            cls._dir_created = True
```

---

## 5. Дублирование в handlers/start.py

### 5.1 _launch_claude* функции

Три почти идентичные функции:
- `_launch_claude()` (lines 170-197)
- `_launch_claude_from_callback()` (lines 198-223)
- `_launch_claude_in_thread()` (lines 224-250)

**Решение:** Унифицировать:

```python
async def _do_launch(
    update: Message | CallbackQuery,
    result: FlowResult,
) -> None:
    """Unified launch handler."""
    # Determine context from update type
    if isinstance(update, Message):
        bot = update.bot
        chat_id = update.chat.id
        thread_id = update.message_thread_id
    else:
        bot = update.bot
        chat_id = update.message.chat.id
        thread_id = update.message.message_thread_id

    # Single implementation
    await launch_with_animation(...)
```

**Экономия:** ~60 строк

### 5.2 _connect_to_session* функции

Две похожие функции:
- `_connect_to_session()` (lines 252-263)
- `_connect_to_session_from_callback()` (lines 264-280)

**Экономия:** ~20 строк

---

## 6. Мелкие улучшения

### 6.1 Дублирование tmux_session_exists()

3 места проверяют существование tmux одинаково:
- `session_manager.py:37-42`
- `session_manager.py:46-51`
- `tmux.py:91-95`

**Решение:** Вынести в `tmux.py`:

```python
def tmux_session_exists(name: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True
    )
    return result.returncode == 0
```

### 6.2 MessageRouterService singleton

**Файл:** `handlers/messages.py:14`

```python
_message_router = MessageRouterService()  # Создаётся при импорте
```

**Решение:** Align с DI pattern — создавать в handler или inject через middleware.

### 6.3 Inline imports

Повторяющиеся inline imports в handlers/start.py:
- `from ..launch_animation import launch_with_animation` (3 раза)

**Решение:** Вынести на уровень модуля.

---

## Порядок выполнения

### Batch 1: High Value (Critical)
1. Унифицировать permission_poller (100 строк)
2. Удалить find_missed_entries (23 строки)
3. Удалить _maybe_start_tasks (8 строк)

### Batch 2: Config
4. Вынести константы в config.py
5. Обновить все файлы использовать settings.*

### Batch 3: Architecture
6. DI middleware для telegram_queue
7. Удалить sys.modules hack
8. Async tmux wrapper

### Batch 4: Code Quality
9. Унифицировать _launch_claude* функции
10. Унифицировать _connect_to_session* функции
11. Вынести tmux_session_exists()

### Batch 5: Legacy Cleanup
12. Мигрировать deprecated ProjectState поля
13. Удалить deprecated поля

---

## Тестирование

### Unit Tests

```bash
PYTHONPATH=src pytest tests/ -v
```

Ожидание: все 229 тестов проходят после каждого batch.

### E2E Checklist

| Тест | Действие | Ожидание |
|------|----------|----------|
| Start project | `/start` | Claude запускается |
| Permission Yes | Нажать Yes | Claude продолжает |
| Permission No | Нажать No | Claude останавливается |
| Send message | Текст | Появляется в tmux |
| Auto-accept | `/auto_accept` | Работает |
| Thread create | `/thread_create` | Топик создаётся |
| Branch create | `/branch_create` | Worktree создаётся |

---

## Definition of Done

- [ ] permission_poller унифицирован (1 функция вместо 2)
- [ ] Dead code удалён (find_missed_entries, _maybe_start_tasks)
- [ ] Константы в config.py
- [ ] sys.modules hack удалён
- [ ] _launch_claude* унифицированы
- [ ] Unit тесты проходят (229)
- [ ] E2E тесты проходят
- [ ] Бот работает стабильно 10+ минут

---

## Метрики

| Метрика | Before Phase 11 | After Phase 11 |
|---------|-----------------|----------------|
| permission_poller.py | ~450 LOC | ~280 LOC |
| handlers/start.py | 527 LOC | ~450 LOC |
| Dead code | ~80 LOC | 0 |
| Hardcoded constants | 15 refs | 0 |
| sys.modules hack | 1 | 0 |
