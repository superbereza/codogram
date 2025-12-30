# Session Binder Design v4

> **Approach:** Telegram Commands для управления сессиями

## Проблема

**Баг:** Thread session mixup — когда новая сессия появляется в одном треде (через /new, /clear), другие треды ошибочно теряют свою привязку.

**Root cause:** `check_session_for_thread()` использует `find_session_for_project(cwd)` который возвращает последнюю сессию **проекта**, а не сессию конкретного треда.

**См. также:**
- [Bug report](../bugs/2025-12-29-thread-session-mixup.md)
- [Research: Thread Session Binding](../research/thread-session-binding-analysis.md)
- [Research: Claude Code Files](../research/claude-code-file-structure.md)

## Ключевой инсайт

После исследования структуры файлов Claude Code:

| Команда | Новая сессия? | Detectable? |
|---------|---------------|-------------|
| `/new` | ДА | history.jsonl sessionId change |
| `/clear` | ДА | history.jsonl sessionId change |
| `/compact` | НЕТ | summary record в session jsonl |

**Вывод:** Проблема только с `/new` и `/clear`. Если эти команды выполняются через Telegram бот, бот **всегда знает** какой thread ждёт новую сессию.

## Решение

### Quick Fix (немедленно)

Удалить вызов `check_session_for_thread()` в `bot.py:1388-1389`. Это остановит баг.

### Long-term Solution

1. **Telegram команды** `/new` и `/clear` в боте
2. **Флаг** `awaiting_new_session` для thread
3. **Привязка** новой сессии к ожидающему thread

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                     Telegram Bot                             │
│                                                              │
│  /new, /clear commands:                                     │
│    1. Set thread.awaiting_new_session = true                │
│    2. tmux send-keys "/new\n" (or /clear)                   │
│    3. Wait for new session via HistoryWatcher               │
│                                                              │
│  on_message:                                                │
│    - Send to tmux (NO check_session_for_thread!)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────────────┐    ┌─────────────────────────────────┐
│  PermissionPoller   │    │        HistoryWatcher           │
│  (unchanged)        │    │   (every 15 sec)                │
│                     │    │                                 │
│                     │    │   For each thread:              │
│                     │    │   - If awaiting_new_session     │
│                     │    │   - Check history.jsonl         │
│                     │    │   - Bind new session            │
└─────────────────────┘    └─────────────────────────────────┘
```

## Изменения в коде

### 1. Удалить check_session_for_thread (Quick Fix)

**Файл:** `src/codogram/bot.py`

```python
# УДАЛИТЬ строки 1388-1389:
# from .history_watcher import check_session_for_thread
# await check_session_for_thread(project, thread, message.bot, start_poller, start_watcher)

# ЗАМЕНИТЬ на:
else:
    # Session binding is handled by:
    # - /new, /clear commands (set awaiting_new_session)
    # - HistoryWatcher (binds new sessions to awaiting threads)
    pass
```

### 2. Добавить команду /new

**Файл:** `src/codogram/bot.py`

```python
@router.message(Command("new"))
async def cmd_new(message: Message):
    """Start new Claude session in current thread."""
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Проект не зарегистрирован. Используй /start")
        return

    thread_id = message.message_thread_id
    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("Thread не найден")
        return

    tmux_name = thread.get_tmux_session(project.project_name)

    # Check tmux exists
    if not is_tmux_session_exists(tmux_name):
        await message.answer("tmux сессия не найдена")
        return

    # Mark thread as awaiting new session
    thread.awaiting_new_session = True
    thread.last_sent_message = None  # Clear fingerprint
    project_manager._save()

    # Send /new to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_keys("/new")

    await message.answer("⏳ Создаю новую сессию...")
```

### 3. Добавить команду /clear

**Файл:** `src/codogram/bot.py`

```python
@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Clear Claude session and start fresh."""
    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Проект не зарегистрирован. Используй /start")
        return

    thread_id = message.message_thread_id
    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("Thread не найден")
        return

    tmux_name = thread.get_tmux_session(project.project_name)

    if not is_tmux_session_exists(tmux_name):
        await message.answer("tmux сессия не найдена")
        return

    # Mark thread as awaiting new session
    thread.awaiting_new_session = True
    thread.last_sent_message = None
    project_manager._save()

    # Send /clear to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_keys("/clear")

    await message.answer("⏳ Очищаю сессию...")
```

### 4. Обновить HistoryWatcher

**Файл:** `src/codogram/history_watcher.py`

```python
async def _check_for_changes(self):
    """Check for session changes and bind awaiting threads."""
    for project in list(self.project_manager.projects.values()):
        if not project.chat_id or not project.cwd:
            continue

        # Check tmux health (existing logic)
        for thread in list(project.threads.values()):
            # ... existing tmux died detection ...
            pass

        # Bind awaiting threads to new sessions
        await self._bind_awaiting_threads(project)


async def _bind_awaiting_threads(self, project: ProjectState):
    """Find new sessions and bind to awaiting threads."""
    for thread in project.threads.values():
        if not thread.awaiting_new_session:
            continue

        # Get tmux session name for this thread
        tmux_name = thread.get_tmux_session(project.project_name)

        # Find session for this specific tmux
        new_session = self._find_session_for_tmux(project.cwd, tmux_name)

        if new_session and new_session != thread.session_id:
            await self._bind_thread_to_session(project, thread, new_session)


def _find_session_for_tmux(self, cwd: str, tmux_name: str) -> str | None:
    """Find latest session that matches this tmux session.

    Strategy: Check if the latest session in history.jsonl for this cwd
    is newer than thread's current session.
    """
    # For now, use simple approach: latest session for project
    # This works because each thread has its own tmux, and we only
    # check threads with awaiting_new_session=true
    return find_session_for_project(cwd)


async def _bind_thread_to_session(
    self,
    project: ProjectState,
    thread: ThreadInfo,
    new_session_id: str
):
    """Bind thread to new session."""
    logger.info(
        f"session_bound: project={project.project_name}, thread={thread.name}, "
        f"old={thread.session_id[:8] if thread.session_id else None}, "
        f"new={new_session_id[:8]}"
    )

    # Cancel old watcher
    if thread.watcher_task:
        thread.watcher_task.cancel()
        thread.watcher_task = None

    # Update binding
    thread.session_id = new_session_id
    thread.jsonl_path = str(compute_jsonl_path(project.cwd, new_session_id))
    thread.awaiting_new_session = False

    # Start new watcher
    thread.watcher_task = asyncio.create_task(
        watch_thread_jsonl(None, project, thread, self.telegram_queue)
    )

    # Restart permission poller
    if thread.poller_task:
        thread.poller_task.cancel()
    from .permission_poller import create_poller_task_for_thread
    thread.poller_task = await create_poller_task_for_thread(
        self.bot, project, thread, self.telegram_queue
    )

    # Notify user
    from .telegram_queue import OutgoingBatch
    batch = OutgoingBatch(
        chat_id=project.chat_id,
        thread_id=thread.thread_id,
        messages=[{"text": "✅ Новая сессия создана"}],
    )
    await self.telegram_queue.enqueue_nowait(batch)

    # Save config
    self.project_manager._save()
```

### 5. Добавить поле awaiting_new_session в ThreadInfo

**Файл:** `src/codogram/session_manager.py`

```python
@dataclass
class ThreadInfo:
    thread_id: int | None  # None for main thread
    name: str
    session_id: str | None = None
    jsonl_path: str | None = None
    awaiting_new_session: bool = False  # ADD THIS
    last_sent_message: str | None = None
    watcher_task: asyncio.Task | None = None
    poller_task: asyncio.Task | None = None
    binding_task: asyncio.Task | None = None
```

## Что удаляем

1. **`check_session_for_thread()`** в `history_watcher.py` — больше не нужен
2. Вызов `check_session_for_thread` в `bot.py:1388-1389`

## Что остаётся

1. **`poll_for_session_thread()`** — для первичного binding новых threads
2. **`watch_thread_jsonl()`** — watcher для thread
3. **`find_session_for_project()`** — используется в `_bind_awaiting_threads`

## Edge Cases

### User does /new in tmux directly

**Риск:** Бот не знает что thread ждёт новую сессию.

**Решение:** Забить. Редкий случай. User может сделать `/start` в Telegram чтобы rebind.

### Multiple threads awaiting simultaneously

**Риск:** Непонятно какой thread получит сессию.

**Решение:** Каждый thread имеет свой tmux. При появлении новой сессии привязываем к первому awaiting thread для этого проекта. Если нужна точность — можно добавить timestamp проверку.

## Тестирование

### Ручное тестирование

1. Зарегистрировать проект через `/start`
2. Создать topic и запустить там Claude
3. Отправить `/new` в topic
4. Проверить что:
   - Claude создал новую сессию
   - Бот показал "✅ Новая сессия создана"
   - Сообщения Claude продолжают приходить

### Тест на mixup bug

1. Иметь два topics с разными Claude сессиями
2. Сделать `/new` в одном topic
3. Проверить что второй topic **НЕ потерял** свою сессию

## Регистрация команд

**Файл:** `src/codogram/main.py`

```python
await bot.set_my_commands([
    BotCommand(command="start", description="Start Claude / show status"),
    BotCommand(command="new", description="Start new Claude session"),
    BotCommand(command="clear", description="Clear and start fresh session"),
    BotCommand(command="session_new", description="Create new Claude thread"),
    BotCommand(command="session_close", description="Close Claude thread"),
    BotCommand(command="restart_session", description="Restart Claude session"),
    BotCommand(command="my_chat_id", description="Show your user ID"),
    BotCommand(command="esc", description="Send Escape to Claude"),
])
```

## Альтернативные подходы

Рассмотренные, но отложенные подходы:

- [Hooks-based approach](alternative/2025-12-29-session-binder-hooks-approach.md) — Claude SessionStart hooks + HTTP server

## Changelog

**v4 (2025-12-29):**
- Switched to Telegram commands approach
- Removed hooks complexity
- Added /new and /clear commands
- Simplified HistoryWatcher logic

**v3 (2025-12-29):**
- Added hooks as primary binding mechanism (SUPERSEDED)

**v2 (2025-12-29):**
- Added content matching fallback (SUPERSEDED)

**v1 (2025-12-29):**
- Initial design with content matching only (SUPERSEDED)
