# Multi-Session Topics Design

## Problem

Сейчас один проект = один tmux = один Claude. Хочется запускать несколько параллельных Claude сессий для одного проекта, каждая в своём топике Telegram.

## Solution

Использовать Telegram Forum Topics. Каждый топик = отдельный tmux + отдельная Claude сессия.

## Telegram API

Боты могут работать с топиками (требуется супергруппа с включёнными топиками):

| Метод | Что делает | Права |
|-------|------------|-------|
| `createForumTopic` | Создать топик | `can_manage_topics` |
| `deleteForumTopic` | Удалить топик со всеми сообщениями | `can_delete_messages` |
| `closeForumTopic` | Закрыть топик | `can_manage_topics` |

## Commands

### `/thread_new [name]`

1. Генерирует имя (магическое слово или пользовательское)
2. Создаёт топик в Telegram
3. Сохраняет `thread_id → name` в config
4. Создаёт tmux `claude-{project}-{name}`
5. Запускает Claude в tmux

**Магические имена (если не указано):**
```python
MAGIC_NAMES = [
    "arcane", "mystic", "ethereal", "celestial", "phantom",
    "cosmic", "astral", "enigmatic", "luminous", "spectral",
    "sublime", "radiant", "obscure", "cryptic", "eldritch",
    "prismatic", "nebulous", "transcendent", "immortal", "mythic",
    # ...
]
```

Выбирается случайное имя, которого нет среди существующих tmux сессий.

### `/thread_close`

1. Спрашивает подтверждение: "Закрыть тред? Топик будет удалён"
2. При подтверждении:
   - Останавливает watcher и poller
   - Убивает tmux сессию
   - Удаляет топик из Telegram
   - Удаляет thread из config

## Session Binding

**Проблема:** Как привязать session_id к треду? В history.jsonl нет информации о tmux, только cwd.

**Решение:** Сопоставлять по user message.

### Алгоритм

```python
async def on_message_in_thread(message, project, thread):
    thread.last_sent_message = message.text
    tmux_session = thread.get_tmux_session(project.project_name)
    send_to_tmux(tmux_session, message.text)

    if not thread.session_id:
        # Запустить быстрый поллинг
        asyncio.create_task(poll_for_session(project, thread))

async def poll_for_session(project, thread, timeout=300, interval=0.5):
    """Быстрый поллинг для привязки session к треду."""
    start = time.time()

    while time.time() - start < timeout:
        # Найти новые (непривязанные) sessions для этого cwd
        new_sessions = find_unbound_sessions(project.cwd)

        for session_id in new_sessions:
            # Прочитать user message из jsonl сессии
            user_msg = get_last_user_message_from_jsonl(session_id)

            if user_msg == thread.last_sent_message:
                # Нашли! Привязываем
                thread.session_id = session_id

                # Отправить пропущенные ответы (missed responses)
                missed = find_missed_entries(get_session_jsonl_path(session_id))
                for entry in missed:
                    await send_entry_to_thread(bot, project, thread, entry)

                # Запустить watcher с текущей позиции
                thread.watcher_task = await start_watcher(project, thread)

                logger.info("session_bound", extra={
                    "thread": thread.name,
                    "session_id": session_id[:8]
                })
                return

        await asyncio.sleep(interval)

    # Таймаут 5 минут
    await bot.send_message(
        project.chat_id,
        "⚠️ Сессия не обнаружена. Проверьте что Claude запущен.",
        message_thread_id=thread.thread_id
    )
```

### Смена сессии (/new, /compact)

Когда пользователь делает `/new` или `/compact` в tmux:
1. Claude создаёт новую сессию
2. Новый session_id появляется в history.jsonl
3. При следующем сообщении в тред:
   - `thread.session_id` не совпадает с текущим в jsonl
   - Сбрасываем `thread.session_id = None`
   - Запускаем быстрый поллинг
   - Находим новый session по user message

### /resume — не поддерживается

`/resume` загружает старую историю, user messages не совпадут с отправленными через Telegram.

**Решение:** Ловить `/resume` и показывать ошибку:
```
⚠️ /resume не поддерживается в мультисессионном режиме
```

## Data Structures

### ThreadInfo (runtime)

```python
@dataclass
class ThreadInfo:
    thread_id: int | None  # None = General topic
    name: str              # mystic, arcane, user-provided

    # Derived from name:
    # tmux_session = f"claude-{project_name}-{name}"

    # Runtime state (from history.jsonl):
    session_id: str | None = None
    jsonl_path: str | None = None

    # Tasks:
    watcher_task: asyncio.Task | None = None
    poller_task: asyncio.Task | None = None
    poll_task: asyncio.Task | None = None  # Быстрый поллинг

    # For session binding:
    last_sent_message: str | None = None

    def get_tmux_session(self, project_name: str) -> str:
        if self.name == "main":
            return f"claude-{project_name}"
        return f"claude-{project_name}-{self.name}"
```

### ProjectState (расширение)

```python
@dataclass
class ProjectState:
    project_name: str
    chat_id: int | None
    cwd: str | None

    # Мультитреды: thread_id -> ThreadInfo
    threads: dict[int | None, ThreadInfo] = field(default_factory=dict)
```

`thread_id = None` означает General topic (основной тред).

## Config Structure

```json
{
  "projects": {
    "codogram": {
      "chat_id": -1003532995083,
      "cwd": "/home/user/dev/codogram",
      "threads": {
        "null": {"name": "main"},
        "12345": {"name": "mystic"},
        "67890": {"name": "arcane"}
      }
    }
  }
}
```

**Ключ** — `thread_id` (строка, `"null"` для General topic)

**Значение** — только `name`

**Выводимые значения (runtime):**
- `tmux_session` = `claude-{project}-{name}`
- `session_id`, `jsonl_path` = из history.jsonl

## Thread Sync on Bot Startup

При старте бота синхронизируем threads с Telegram:

```python
async def sync_threads_with_telegram(bot: Bot, project: ProjectState):
    """Sync config threads with actual Telegram topics."""
    if not project.chat_id:
        return

    # Получить список топиков из Telegram
    # Примечание: Bot API не имеет метода getForumTopics,
    # но можно слушать ForumTopicCreated/Deleted события
    # или использовать MTProto (Telethon/Pyrogram)

    # Альтернатива: при получении сообщения из неизвестного топика
    # автоматически добавлять его в config
```

**Ограничение Telegram Bot API:** В сообщениях приходит только `message_thread_id`, не имя топика. Имя доступно только:
1. При создании топика (ForumTopicCreated service message)
2. Через MTProto API (не Bot API)

**Решение:**
- При `/thread_new` — сохраняем имя в config
- При сообщении из неизвестного thread_id — запрашиваем имя или используем thread_id как имя

## Message Routing

При получении сообщения:

```python
@router.message()
async def on_message(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id  # None для General

    project = project_manager.get_by_chat(chat_id)
    if not project:
        return

    # Найти ThreadInfo для этого топика
    thread = project.threads.get(thread_id)
    if not thread:
        # Неизвестный топик — игнорируем или автосоздание?
        return

    thread.last_sent_message = message.text
    tmux_session = thread.get_tmux_session(project.project_name)
    send_to_tmux(tmux_session, message.text)

    if not thread.session_id:
        asyncio.create_task(poll_for_session(project, thread))
```

## Watcher per Thread

Каждый тред имеет свой watcher, следящий за своим jsonl файлом:

```python
async def watcher_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo):
    path = Path(thread.jsonl_path)

    async for entry in watch_jsonl(path):
        await send_entry_to_thread(bot, project, thread, entry)

async def send_entry_to_thread(bot: Bot, project: ProjectState,
                                thread: ThreadInfo, entry: ParsedEntry):
    # Отправить в конкретный топик
    await bot.send_message(
        project.chat_id,
        format_entry(entry),
        message_thread_id=thread.thread_id,
        parse_mode="Markdown"
    )
```

## Edge Cases

| Случай | Поведение |
|--------|-----------|
| Пустой jsonl (нет user message) | Пропускаем, ждём следующего поллинга |
| Одинаковое сообщение в двух тредах | Маловероятно; если случится — первый найденный |
| Tmux умер | Уведомляем в тред |
| Таймаут 5 минут | Показать ошибку в треде |
| /resume | Показать ошибку "не поддерживается" |
| Неизвестный thread_id | Игнорируем сообщение |
| Бот перезапустился | Sync threads с config, восстановить tmux connections |

## Future: /branch_new (Git Worktrees)

Отдельный дизайн для создания сессий в git worktrees:
- Каждая сессия в отдельной директории
- Полная изоляция session_id (разные cwd)
- Поддержка веток
