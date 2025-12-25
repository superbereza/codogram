# ProjectState Refactoring - Design

**Status:** Implemented

## Проблема

Текущая архитектура `SessionState` смешивает две концепции:
1. **Связь tmux ↔ Telegram** (нужна сразу при создании tmux)
2. **Связь с Claude** (появляется когда Claude стартует через hook)

Это создаёт проблемы:
- Поллер не может стартовать до hook (нет сессии)
- Trust dialog не показывается в Telegram
- Порядок создания chat/Claude имеет значение

## Решение: ProjectState

Единый источник правды для проекта. Поля заполняются постепенно из разных источников.

```python
@dataclass
class ProjectState:
    """Всё что знаем о проекте. Поля заполняются постепенно."""
    project_name: str

    # Telegram (появляется при /start)
    chat_id: int | None = None

    # Filesystem
    cwd: str | None = None

    # Tmux (появляется при /start или hook)
    tmux_session: str | None = None
    poller_task: asyncio.Task | None = None

    # Claude (появляется при hook)
    claude_session_id: str | None = None
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = None
```

## Ключевая логика: `_maybe_start_tasks`

```python
async def _maybe_start_tasks(self, project: ProjectState):
    """Запустить таски если есть все нужные данные."""

    # Поллер: нужен tmux_session + chat_id
    if project.tmux_session and project.chat_id:
        if not project.poller_task or project.poller_task.done():
            project.poller_task = await start_poller(project)

    # Watcher: нужен jsonl_path + chat_id
    if project.jsonl_path and project.chat_id:
        if not project.watcher_task or project.watcher_task.done():
            project.watcher_task = await start_watcher(project)
```

## Два входа, один результат

```python
# /start вызывает:
await manager.update_from_telegram(project_name, chat_id, cwd)

# Hook вызывает:
await manager.update_from_hook(session_id, cwd, tmux_session)

# Оба вызывают _maybe_start_tasks — таски стартуют когда всё есть
```

## Сценарии

| Сценарий | Первый вызов | Второй вызов | Результат |
|----------|--------------|--------------|-----------|
| /start → Claude | update_from_telegram (chat_id) | update_from_hook (tmux) | tasks start |
| Claude → /start | update_from_hook (tmux) | update_from_telegram (chat_id) | tasks start |
| Чат → Claude руками | update_from_telegram (chat_id) | update_from_hook (tmux) | tasks start |
| Claude работает → чат | update_from_hook был давно | update_from_telegram (chat_id) | tasks start |

**Порядок не важен** — каждый update проверяет "можно ли уже запустить таски?"

## Логика /start

```python
async def cmd_start(project_name, chat_id, path):
    project = manager.get_or_create(project_name)
    project.chat_id = chat_id

    # Кейс 1: Claude работает — подключаемся
    if project.claude_session_id:
        await manager.maybe_start_tasks(project)
        await message.answer(f"Claude активен в `{project.tmux_session}`")
        return

    # Claude не работает — решаем про tmux
    convention = f"claude-{project_name}"

    if project.tmux_session and is_tmux_alive(project.tmux_session):
        if project.tmux_session == convention:
            # Кейс 2: наш tmux — переиспользуем
            send_keys(convention, "claude", "Enter")
        else:
            # Кейс 3: чужой tmux — новый рядом
            create_tmux(convention, path)
            project.tmux_session = convention
    else:
        # Кейс 4: нет tmux — создаём
        create_tmux(convention, path)
        project.tmux_session = convention

    send_keys(project.tmux_session, "claude", "Enter")
    await manager.maybe_start_tasks(project)
```

## SessionEnd

При завершении Claude (hook SessionEnd):

```python
def handle_session_end(session_id):
    project = find_project_by_session(session_id)

    # Race condition protection
    if project.claude_session_id != session_id:
        return  # уже новая сессия, игнорируем

    # Очищаем Claude-related
    project.claude_session_id = None
    project.jsonl_path = None

    # Останавливаем таски
    if project.watcher_task:
        project.watcher_task.cancel()
        project.watcher_task = None
    if project.poller_task:
        project.poller_task.cancel()
        project.poller_task = None

    # Оставляем: chat_id, cwd, tmux_session
```

| Поле | Действие при SessionEnd |
|------|------------------------|
| chat_id, cwd | Оставляем |
| tmux_session | Оставляем |
| poller_task | Останавливаем |
| watcher_task | Останавливаем |
| claude_session_id | Очищаем |
| jsonl_path | Очищаем |

## tmux lifecycle

**Конвенция именования:** `claude-{project_name}`

**При /start:**
- Наш tmux жив → переиспользуем (send_keys "claude")
- Чужой tmux → создаём новый по конвенции рядом, старый не трогаем
- Нет tmux → создаём по конвенции

**При SessionEnd:**
- tmux НЕ убиваем (может пригодиться, занимает мало памяти)
- Убивается только при пересоздании в /start

## Персистентность (.config.json)

```json
{
  "projects": {
    "my-project": {
      "chat_id": -123456789,
      "cwd": "/home/user/dev/my-project"
    }
  },
  "sessions": {
    "my-project": {
      "tmux_session": "claude-my-project",
      "claude_session_id": "abc-123",
      "jsonl_path": "/home/user/.claude/projects/.../abc-123.jsonl"
    }
  }
}
```

- **projects** — постоянные данные (chat_id, cwd)
- **sessions** — временные данные (tmux, claude), восстанавливаются с проверкой

**При restore:**
1. Загружаем projects и sessions
2. Для каждой session проверяем:
   - tmux жив? (`tmux has-session`)
   - jsonl существует?
3. Если да — восстанавливаем таски
4. Если нет — очищаем sessions, оставляем projects

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Запуск Claude / показ статуса (если уже работает) |
| `/restart_session` | Перезапуск Claude с подтверждением |
| `/esc` | Отправить Escape в tmux |
| `/my_chat_id` | Показать ID чата |

### /restart_session

```
Перезапустить Claude сессию?

[Да, перезапустить]  [Отмена]
```

При подтверждении:
1. Если Claude работает — kill tmux session
2. Создать новый tmux по конвенции
3. Запустить Claude

## Будущие улучшения

- **Read-only режим** — подключение к Claude без tmux (только watcher, без поллера и отправки)
- **Multi-device** — один проект в нескольких чатах
- **Session picker** — выбор сессии для подключения (для ноута без tmux)
