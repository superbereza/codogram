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

### Источники данных

```
Persistent (config.json):
  - chat_id → project_name
  - project_name → cwd

Dynamic (computed):
  - cwd → session_id        ← history.jsonl
  - cwd → tmux_session      ← tmux list-panes или конвенция
  - session_id → jsonl_path ← вычисляем
```

### Логика

```
/start chat_id project_name cwd:
  1. Сохраняем в config
  2. session_id ← find_in_history(cwd)
  3. tmux ← find_tmux_by_cwd(cwd) или конвенция
  4. jsonl_path ← compute(cwd, session_id)
  5. Запускаем poller + watcher

restore (при старте бота):
  Для каждого project в config → тот же алгоритм

periodic (каждые 10s):
  Для каждого активного project:
    - Проверяем session_id в history.jsonl
    - Если изменился → переподключаем watcher
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

Нагрузка: ~1 stat() каждые 10s на проект = ничто.

## Что удаляем

1. `hooks/session-start.sh` — больше не нужен
2. `hooks/session-end.sh` — больше не нужен
3. HTTP endpoints `/session/register`, `/session/unregister`
4. `update_from_hook()` в session_manager
5. `handle_session_end()` в session_manager
6. Секция `sessions` в config.json

## Что добавляем

1. `HistoryWatcher` — читает history.jsonl, отслеживает изменения
2. `find_session_for_project(cwd)` — поиск session_id по cwd
3. `find_tmux_by_cwd(cwd)` — поиск tmux сессии по cwd
4. Periodic refresh task

## Риски

1. **history.jsonl формат изменится** — маловероятно, internal API
2. **tmux поиск ненадёжен** — fallback на конвенцию имён
3. **Большой history.jsonl** — читаем только новые строки

## Миграция

1. Создаём ветку `with-hooks` для сохранения текущего состояния
2. В `main` реализуем новую архитектуру
3. Hooks остаются в репозитории как deprecated (для тех кто хочет мгновенную реакцию)
