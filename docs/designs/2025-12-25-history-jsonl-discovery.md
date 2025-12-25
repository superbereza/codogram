# Архитектурное решение: history.jsonl вместо hooks

**Статус:** Принято
**Дата:** 2025-12-25

## Контекст

При отладке "потерянных" сессий (Claude работает, но watcher не подключен) обнаружили, что `~/.claude/history.jsonl` содержит mapping project → sessionId.

Это открыло возможность отказаться от hooks как источника session_id.

## Находка: history.jsonl

```json
{
  "display": "сообщение пользователя",
  "project": "/home/superbereza/dev/personal-agent",
  "sessionId": "c2698774-d17d-487a-bd78-29dc93adadd6",
  "timestamp": 1766673470986
}
```

**Свойства:**
- Обновляется при каждом сообщении пользователя
- Держится открытым Claude (видно в lsof)
- Содержит точный project path и sessionId
- Работает для ВСЕХ сессий, включая запущенные до установки bridge

## Сравнение подходов

### Hooks (текущий)

| Плюсы | Минусы |
|-------|--------|
| Мгновенная реакция на старт | Требует настройки ~/.claude/settings.json |
| Точный tmux_session | Race conditions с /start |
| Session end detection | Не работает для уже запущенных сессий |
| | Сложность отладки |

### history.jsonl (новый)

| Плюсы | Минусы |
|-------|--------|
| Zero config — работает сразу | Задержка ~10-30s при смене сессии |
| Работает для всех сессий | Нет tmux_session (нужна конвенция) |
| Единый источник правды | Нет session end detection |
| Нет race conditions | |
| Проще архитектура | |

## Анализ сценариев

| Сценарий | С hooks | С history.jsonl | Победитель |
|----------|---------|-----------------|------------|
| /start → Claude | watcher сразу | watcher через ~10s | hooks (+10s) |
| Claude → /start | если hook был настроен | работает сразу | **history** |
| Новый пользователь | нужно настроить hooks | **работает сразу** | **history** |
| Перезапуск бота | нужны сохранённые sessions | читаем history | **history** |
| Смена сессии (/resume) | мгновенно | через periodic poll | hooks (+10s) |

**Ключевой инсайт:** Сценарий "новый пользователь" — первое с чем столкнётся каждый. History.jsonl работает сразу без настройки.

## Решение

**Отказываемся от hooks в пользу history.jsonl.**

Причины:
1. **Zero config** — главное преимущество для новых пользователей
2. **Задержка 10-30s не критична** — пользователь не заметит
3. **Упрощение архитектуры** — убираем HTTP endpoints, race conditions, hooks config
4. **Self-healing** — periodic refresh автоматически подхватывает новые сессии

## Новая архитектура

### Мультисессии (структура готова, реализация на будущее)

Один project (cwd) может иметь **несколько активных Claude сессий**:
- Основной Claude в `claude-personal-agent`
- Второй Claude в `personal-agent`
- Subagents (пишут в `agent-*.jsonl`)

**MVP:** работаем с одной сессией. Структура данных (dict) готова к мультисессиям.

**При обнаружении нескольких tmux:**
```
Найдено несколько tmux сессий с Claude:
[claude-personal-agent] — active 5m ago
[personal-agent] — active 2h ago

Какую подключить?
```
Пользователь выбирает одну → подключаем только её.

**Ключевой инсайт: независимость watcher и poller**

| Компонент | Использует | Для чего |
|-----------|------------|----------|
| Watcher | session_id → jsonl | Читает output Claude |
| Poller | tmux_session | Capture screen, send keys |

Им **не нужно знать друг о друге**. Связь session_id ↔ tmux_session не требуется!

**Модель данных:**

```python
@dataclass
class SessionInfo:
    """Информация об одной Claude сессии (для watcher)."""
    session_id: str
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = None
    last_activity: float = 0  # timestamp последней активности

@dataclass
class ProjectState:
    """Состояние проекта с поддержкой нескольких сессий."""
    project_name: str
    chat_id: int | None = None
    cwd: str | None = None

    # Watchers: session_id → SessionInfo (из history.jsonl)
    sessions: dict[str, SessionInfo] = field(default_factory=dict)

    # Pollers: tmux_session → Task (найдены по cwd)
    pollers: dict[str, asyncio.Task] = field(default_factory=dict)
```

**Принципы:**
- Watcher'ы работают параллельно, каждый следит за своим jsonl
- Poller'ы работают параллельно, каждый следит за своим tmux
- Связь между ними не нужна

**Cleanup:** сессии без активности > 30 дней удаляются автоматически.

### Источники данных

```
Persistent (config.json):
  - chat_id → project_name
  - project_name → cwd

Dynamic (computed):
  - cwd → session_ids[]     ← history.jsonl (несколько!)
  - cwd → tmux_sessions[]   ← tmux list-panes (несколько!)
  - session_id → jsonl_path ← вычисляем
```

### Поиск tmux по cwd

```bash
tmux list-panes -a -F "#{pane_current_path} #{session_name}" | grep "^$cwd "
```

Возвращает все tmux сессии, где хотя бы один pane в нужной директории.

### Логика

```
/start chat_id project_name cwd:
  1. Сохраняем в config
  2. session_ids[] ← find_all_sessions(cwd)
  3. tmux_sessions[] ← find_all_tmux_by_cwd(cwd)

  4. Если tmux_sessions.length > 1:
     - Показываем список с кнопками выбора
     - Ждём выбора пользователя
     - Продолжаем с выбранным tmux

  5. Для выбранного session_id (последний по timestamp):
     - jsonl_path ← compute(cwd, session_id)
     - Запускаем watcher если jsonl существует

  6. Для выбранного tmux_session:
     - Запускаем poller

restore (при старте бота):
  Для каждого project в config:
    - tmux ← find_tmux_by_convention(project_name)
    - session_id ← find_latest_session(cwd)
    - Запускаем watcher + poller

periodic (каждые 15s):
  Для каждого активного project:
    - Проверяем session_id в history.jsonl (изменился?)
    - Если да → перезапускаем watcher
    - Cleanup сессий старше 30 дней
```

**Примечание:** При restore не показываем выбор — берём по конвенции `claude-{project}` или первый найденный.

### Permission routing

**MVP:** один poller → один источник permissions. Callback содержит `tmux_session`.

**Мультисессии (будущее):** если несколько Claude просят permission одновременно, добавляем префикс:

```
[claude-personal-agent] Permission request:
Bash: rm -rf /tmp/test
[Allow] [Deny]

[personal-agent] Permission request:
Bash: git push
[Allow] [Deny]
```

### Оптимизация polling

```python
last_mtime = 0
last_size = 0

def check_history():
    stat = history_path.stat()

    # Быстрая проверка — файл не изменился
    if stat.st_mtime == last_mtime:
        return None

    # Читаем только новые строки
    if stat.st_size > last_size:
        with open(history_path) as f:
            f.seek(last_size)
            new_lines = f.readlines()
        last_size = stat.st_size
        # Парсим только новое

    last_mtime = stat.st_mtime
```

Нагрузка: ~1 stat() каждые 15s на проект = ничто.

## Что удаляем

1. `hooks/session-start.sh` — больше не нужен
2. `hooks/session-end.sh` — больше не нужен
3. HTTP endpoints `/session/register`, `/session/unregister`
4. `update_from_hook()` в session_manager
5. `handle_session_end()` в session_manager
6. Секция `sessions` в config.json

## Что добавляем

1. `SessionInfo` dataclass — информация об одной сессии (session_id, watcher_task, last_activity)
2. `ProjectState.sessions` — dict (готов к мультисессиям, MVP использует одну)
3. `ProjectState.pollers` — dict (готов к мультисессиям, MVP использует один)
4. `HistoryReader` — читает history.jsonl инкрементально, кэширует session_id по cwd
5. `find_all_sessions_for_project(cwd)` — поиск ВСЕХ session_id по cwd
6. `find_all_tmux_by_cwd(cwd)` — поиск ВСЕХ tmux сессий по cwd
7. UI выбора tmux при /start (если найдено > 1)
8. Periodic refresh task с cleanup старых сессий (30 дней)

## Риски

1. **history.jsonl формат изменится** — маловероятно, internal API
2. **tmux list-panes формат изменится** — маловероятно, стабильный API
3. **Большой history.jsonl** — читаем только новые строки (инкрементально)
4. **Несколько tmux с одним cwd** — показываем UI выбора, пользователь решает
5. **Session сменилась (/resume)** — periodic refresh подхватит через 15s

## Миграция

1. Создаём ветку `with-hooks` для сохранения текущего состояния
2. В `main` реализуем новую архитектуру
3. Hooks остаются в репозитории как deprecated (для тех кто хочет мгновенную реакцию)
