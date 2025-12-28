# Missed Responses Design

## Problem

При смене сессии (`/start`, `/new`, `/resume`, `/compact`) watcher начинает следить с конца jsonl файла и пропускает ответы Claude, которые уже записаны.

**Race condition:**
1. `/start` → Claude запускается в tmux
2. `refresh_project_session()` → Claude ещё НЕ записал в history.jsonl → не находит сессию
3. `jsonl_path = None` → watcher не стартует
4. Пользователь пишет сообщение → `check_session_for_project()` → всё ещё нет записи
5. Claude записывает в history.jsonl
6. Следующее сообщение → находит → watcher стартует, но первый ответ уже пропущен

**Для /new и /compact аналогично:** старая сессия есть, появляется новая, watcher перезапускается с конца нового файла.

## Solution

При запуске watcher для новой/изменённой сессии — сначала найти и отправить все ответы после последнего user message, потом продолжить слежение.

## Design Decisions

### Когда подхватывать пропущенные ответы?
**При любом изменении session_id** — покрывает `/start`, `/new`, `/resume`, `/compact`.

На каждом сообщении пользователя вызывается `check_session_for_project`, который сравнивает текущий session_id с новым из history.jsonl. При `changed=True` → подхват ответов.

### Где разместить логику?
**В watcher.py** — вся логика работы с jsonl в одном месте, меньше дублирования. Добавляем параметр `send_missed=True`.

### Как определить "пропущенные ответы"?
**Все entries после последнего user message** — читаем jsonl, находим последний `type: "user"`, отправляем все `type: "assistant"` после него.

Покрывает случай когда Claude отвечает несколькими tool calls подряд.

### Как читать jsonl?
**Весь файл** — jsonl новой сессии небольшой (десятки KB максимум). Оптимизация не нужна, простота важнее.

## Implementation

### watcher.py

**Новая функция:**
```python
def find_missed_entries(path: Path) -> list[ParsedEntry]:
    """Найти все ответы после последнего user message."""
    if not path.exists():
        return []

    try:
        entries = []
        with open(path) as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("type") == "user":
                    entries = []  # сбросить — начинаем заново после user
                else:
                    parsed = parse_jsonl_entry(entry)
                    if parsed:
                        entries.append(parsed)
        return entries
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"find_missed_entries error: {e}")
        return []
```

**Изменение сигнатур:**
```python
async def create_watcher_task(bot: Bot, project: ProjectState,
                              send_missed: bool = False) -> asyncio.Task:
    return asyncio.create_task(watcher_for_session(bot, project, send_missed))

async def watcher_for_session(bot: Bot, project: ProjectState,
                              send_missed: bool = False):
    # ... existing setup ...

    if send_missed:
        missed = find_missed_entries(path)
        logger.info(f"Sending {len(missed)} missed entries")
        for entry in missed:
            # отправить как обычно (TEXT, TOOL_USE)

    # продолжить слежение с текущей позиции
```

**Таймаут 5 минут:**
- Если jsonl файл не появился за 5 минут → отправить "⚠️ Сессия не обнаружена. Проверьте что Claude запущен."

### session_manager.py

```python
async def _maybe_start_tasks(self, project, start_poller, start_watcher,
                             send_missed: bool = False):
    # ... poller logic unchanged ...

    if project.jsonl_path and project.chat_id:
        if not project.watcher_task or project.watcher_task.done():
            project.watcher_task = await start_watcher(project, send_missed)
```

### history_watcher.py

**check_session_for_project:**
```python
if changed:
    # ...cancel old watcher...
    await project_manager._maybe_start_tasks(
        project, start_poller, start_watcher,
        send_missed=True
    )
```

**HistoryWatcher._check_for_changes:** аналогично передавать `send_missed=True`.

### bot.py

**Унифицировать текст сообщений (строки 224-227 и 316-320):**

Было:
```python
if project.session_id:
    await message.answer(f"Подключено. Сессия: `{project.session_id[:8]}...`")
else:
    await message.answer("Подключено. Ожидание сессии Claude.")
```

Станет:
```python
await message.answer(
    f"Claude запущен в `{project.tmux_session}`\n"
    f"Подключиться: `tmux attach -t {project.tmux_session}`",
    parse_mode="Markdown",
)
```

Убрать "Ожидание регистрации сессии." отовсюду.

### main.py

```python
async def start_watcher(project: ProjectState, send_missed: bool = False) -> asyncio.Task:
    from .watcher import create_watcher_task
    return await create_watcher_task(bot, project, send_missed)
```

## Error Handling

| Случай | Поведение |
|--------|-----------|
| jsonl не существует | `find_missed_entries` → пустой список, watcher ждёт появления |
| Нет user message в файле | Отправляем все entries (теоретически невозможно) |
| Файл пустой | Пустой список |
| Ошибка парсинга | Логируем, возвращаем пустой список |
| Таймаут 5 минут | Сообщение пользователю "⚠️ Сессия не обнаружена" |
