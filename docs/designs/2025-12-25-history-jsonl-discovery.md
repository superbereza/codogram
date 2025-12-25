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

### Терминология

| Термин | Что это | Время жизни |
|--------|---------|-------------|
| **tmux_session** | tmux сессия (`claude-personal-agent`) | Долго (дни, недели) |
| **session_id** | UUID сессии Claude | Меняется при /new, /compact, /resume |

**Связь:** Один tmux содержит много session_id за время жизни, но активный — всегда один.

```
tmux: claude-personal-agent
  └── 10:00 — session_id: aaa (/new)
  └── 11:00 — session_id: bbb (/compact)
  └── 12:00 — session_id: ccc (/resume)
  └── сейчас — ccc (активный)
```

### Мультисессии (future work)

Один cwd может иметь несколько tmux сессий (разные контексты работы).

**При обнаружении нескольких tmux:**
```
Найдено несколько tmux сессий с Claude:
[claude-personal-agent] — active 5m ago
[personal-agent] — active 2h ago

Какую подключить?
```
Пользователь выбирает одну → подключаем только её.

**Несколько tmux одновременно — future work**, пока не понятен UX.

### Независимость watcher и poller

| Компонент | Использует | Для чего |
|-----------|------------|----------|
| Watcher | session_id → jsonl | Читает output Claude |
| Poller | tmux_session | Capture screen, send keys |

Им **не нужно знать друг о друге**. Связь session_id ↔ tmux_session не требуется!

### Модель данных

```python
@dataclass
class ProjectState:
    """Состояние проекта."""
    project_name: str
    chat_id: int | None = None
    cwd: str | None = None

    # Watcher (один активный session_id)
    session_id: str | None = None
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = None

    # Poller (один выбранный tmux)
    tmux_session: str | None = None
    poller_task: asyncio.Task | None = None
```

**Принципы:**
- Один watcher на проект (следит за активным session_id)
- Один poller на проект (следит за выбранным tmux)
- При смене session_id (через periodic refresh) — перезапускаем watcher

### Источники данных

```
Persistent (config.json):
  - chat_id → project_name
  - project_name → cwd

Dynamic (computed):
  - cwd → session_id      ← history.jsonl (последний по timestamp)
  - cwd → tmux_session    ← tmux list-panes (выбор если > 1)
  - session_id → jsonl_path ← вычисляем по формуле
```

### Формат путей

```
~/.claude/
├── history.jsonl                              # все сессии всех проектов
└── projects/
    └── {cwd.replace("/", "-")}/               # например: -home-user-dev-project
        └── {session_id}.jsonl                 # например: c2698774-d17d-487a-bd78-29dc93adadd6.jsonl
```

**Формула jsonl_path:**
```python
def compute_jsonl_path(cwd: str, session_id: str) -> Path:
    project_hash = cwd.replace("/", "-")
    return Path.home() / ".claude" / "projects" / project_hash / f"{session_id}.jsonl"
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

  # Discovery tmux (для poller)
  2. tmux_list ← find_all_tmux_by_cwd(cwd)
  3. Если len(tmux_list) == 0 → "Claude не найден в tmux"
  4. Если len(tmux_list) == 1 → tmux_session = tmux_list[0]
  5. Если len(tmux_list) > 1 → показываем выбор, ждём ответа

  # Discovery session (для watcher)
  6. session_id ← find_latest_session(cwd)  # последний по timestamp
  7. jsonl_path ← compute_jsonl_path(cwd, session_id)

  # Start tasks
  8. Запускаем poller(tmux_session)
  9. Запускаем watcher(jsonl_path) если файл существует

restore (при старте бота):
  Для каждого project в config:
    - tmux_session ← find_tmux_by_convention(project_name) или первый найденный
    - session_id ← find_latest_session(cwd)
    - Запускаем watcher + poller (без UI выбора)

periodic (каждые 15s):
  Для каждого активного project:
    - new_session_id ← find_latest_session(cwd)
    - Если new_session_id != project.session_id:
        - Останавливаем старый watcher
        - Запускаем новый watcher
        - Обновляем project.session_id
```

### Permission routing

Один poller → один источник permissions. Callback содержит `tmux_session`.

### Оптимизация polling

```python
last_mtime = 0
last_size = 0
session_cache: dict[str, str] = {}  # cwd → session_id

def check_history():
    stat = history_path.stat()

    # Быстрая проверка — файл не изменился
    if stat.st_mtime == last_mtime:
        return session_cache

    # Файл уменьшился (truncated/recreated) → сбрасываем
    if stat.st_size < last_size:
        last_size = 0
        session_cache.clear()

    # Читаем только новые строки
    if stat.st_size > last_size:
        with open(history_path) as f:
            f.seek(last_size)
            new_lines = f.readlines()
        last_size = stat.st_size

        # Парсим с защитой от битого JSON
        for line in new_lines:
            try:
                entry = json.loads(line)
                cwd = entry.get("project")
                session_id = entry.get("sessionId")
                if cwd and session_id:
                    session_cache[cwd] = session_id
            except json.JSONDecodeError:
                continue  # пропускаем битые строки

    last_mtime = stat.st_mtime
    return session_cache
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

1. `ProjectState` упрощённый — session_id, jsonl_path, tmux_session, tasks
2. `HistoryReader` — читает history.jsonl инкрементально, кэширует session_id по cwd
3. `find_latest_session(cwd)` — последний session_id для cwd из history.jsonl
4. `find_all_tmux_by_cwd(cwd)` — поиск tmux сессий по cwd
5. `compute_jsonl_path(cwd, session_id)` — формула пути к jsonl
6. UI выбора tmux при /start (если найдено > 1)
7. Periodic refresh task (15s) — обновление session_id при смене

### Cleanup

Cleanup по mtime jsonl файла (не храним last_activity):

```python
def should_cleanup(jsonl_path: Path) -> bool:
    if not jsonl_path.exists():
        return True  # файл удалён
    mtime = jsonl_path.stat().st_mtime
    age_days = (time.time() - mtime) / 86400
    return age_days > 30
```

При restore/periodic: если `should_cleanup(jsonl_path)` → не восстанавливаем/удаляем session_id.

## Ограничения

1. **Один Claude на tmux сессию** — split panes с несколькими Claude не поддерживаются
2. **cwd фиксируется при /start** — команда `cd` внутри Claude не отслеживается
3. **Session end не детектируется явно** — cleanup по mtime (30 дней)

## Риски

1. **history.jsonl формат изменится** — маловероятно, internal API
2. **tmux list-panes формат изменится** — маловероятно, стабильный API
3. **Большой history.jsonl** — читаем только новые строки (инкрементально)
4. **Несколько tmux с одним cwd** — показываем UI выбора, пользователь решает
5. **Session сменилась (/new, /resume)** — periodic refresh подхватит через 15s
6. **history.jsonl truncated** — сбрасываем кэш и читаем заново
7. **Битый JSON в history.jsonl** — пропускаем строку, продолжаем

## Миграция

1. Создаём ветку `with-hooks` для сохранения текущего состояния
2. В `main` реализуем новую архитектуру
3. Hooks остаются в репозитории как deprecated (для тех кто хочет мгновенную реакцию)
