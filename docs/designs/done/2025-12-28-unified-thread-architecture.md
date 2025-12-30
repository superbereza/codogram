# Unified Thread Architecture

**Статус**: Design
**Дата**: 2025-12-28

## Проблема

Сообщения из топиков дублируются в General чат.

**Пример бага (02:04 MSK):**
1. Пользователь отправляет сообщение в топик "modularization"
2. Claude отвечает
3. Ответ появляется И в топике И в General

## Контекст: Три типа чатов

| Тип | chat.id | message_thread_id | Сессий Claude |
|-----|---------|-------------------|---------------|
| Private | > 0 | всегда None | 1 |
| Simple Group | < 0 | всегда None | 1 |
| Forum Group | < 0 (-100...) | None или int | 1+ (General + топики) |

Бот должен корректно работать со всеми тремя типами.

## Текущая архитектура (сломанная)

```
ProjectState
├── session_id         ← Legacy поля для General/Private/Simple
├── jsonl_path
├── watcher_task       ← Отправляет БЕЗ message_thread_id
├── tmux_session
├── poller_task
└── threads: {
      456: ThreadInfo  ← Для топиков Forum Group
           ├── session_id
           ├── jsonl_path
           └── watcher_task  ← Отправляет С message_thread_id
    }
```

**Проблема:** Два параллельных механизма:
1. Legacy (project.*) - для General/Private/Simple
2. Multi-thread (project.threads[id]) - для топиков Forum

Когда в Forum Group есть топики, оба механизма работают одновременно и конфликтуют.

## Механизм бага

```
1. User → топик "modularization" (thread_id=456)
2. poll_for_session_thread() находит сессию, сохраняет в thread.session_id
3. watch_thread_jsonl() отправляет в топик ✓

4. Параллельно: history_watcher._check_for_changes() каждые 15 сек
5. Видит project.session_id устарел
6. find_session_for_project() находит ТУ ЖЕ сессию (последняя в history.jsonl)
7. Запускает legacy watcher_task → отправляет в General ✗

Результат: Два watcher-а на один jsonl → дублирование
```

## Корневая причина

### 1. Нет изоляции сессий по thread_id

`find_session_for_project(cwd)` ищет в history.jsonl:
```json
{"project": "/path/to/project", "sessionId": "abc123"}
```

**Нет информации о thread_id!** Любой thread может "украсть" сессию другого.

### 2. Legacy и multi-thread конфликтуют

```python
# history_watcher.py _check_for_changes()
if project.threads:
    continue  # Пропускаем если есть threads
```

Но:
- Legacy watcher может быть запущен ДО создания threads
- Проверка пропускает ВЕСЬ проект, не отдельные watchers

## Предлагаемая архитектура

```
ProjectState
└── threads: {
      None: ThreadInfo(name="main")     ← Private/Simple/Forum General
           ├── session_id
           ├── jsonl_path
           └── watcher_task  → message_thread_id=None
      456: ThreadInfo(name="mystic")    ← Forum Topic
           ├── session_id
           ├── jsonl_path
           └── watcher_task  → message_thread_id=456
    }

# УДАЛИТЬ legacy поля:
# - project.session_id
# - project.jsonl_path
# - project.watcher_task
```

### Принцип: thread_id=None это тоже thread

| Сценарий | thread_id | threads key | name | tmux |
|----------|-----------|-------------|------|------|
| Private | None | threads[None] | "main" | claude-{project} |
| Simple Group | None | threads[None] | "main" | claude-{project} |
| Forum General | None | threads[None] | "main" | claude-{project} |
| Forum Topic | 456 | threads[456] | "mystic" | claude-{project}-mystic |

### Определение tmux имени

```python
def get_tmux_session(self, project_name: str) -> str:
    if self.name == "main":
        return f"claude-{project_name}"
    return f"claude-{project_name}-{self.name}"
```

## Session Binding: poll_for_session_thread для всех

### Проблема find_session_for_project

Ищет последнюю сессию в history.jsonl по cwd. Не различает threads.

### Решение: find_session_by_user_message

`poll_for_session_thread` использует другой подход:

```python
result = find_session_by_user_message(project.cwd, thread.last_sent_message)
```

Сканирует ВСЕ jsonl файлы, находит где последнее user сообщение совпадает с отправленным.

**Преимущества:**
- Гарантирует что каждый thread привяжется к СВОЕЙ сессии
- Работает для thread_id=None так же как для thread_id=456
- Не зависит от порядка записей в history.jsonl

### Единый flow

```python
# on_message (для ВСЕХ случаев)
thread = project.threads.get(thread_id)
if not thread:
    name = "main" if thread_id is None else get_magic_name()
    thread = ThreadInfo(thread_id=thread_id, name=name)
    project.threads[thread_id] = thread

tmux = TmuxSession(thread.get_tmux_session(project.project_name), project.cwd)
tmux.send(message.text)

if not thread.session_id:
    thread.last_sent_message = message.text
    thread.binding_task = asyncio.create_task(
        poll_for_session_thread(project, thread, bot, ...)
    )
```

## Миграция

### При загрузке конфига

```python
def _load_projects(self):
    for project_name, data in saved_projects.items():
        project = ProjectState(project_name=project_name)
        project.chat_id = data.get("chat_id")
        project.cwd = data.get("cwd")

        # Migrate legacy → threads[None]
        if data.get("session_id") or data.get("cwd"):
            if None not in project.threads:
                project.threads[None] = ThreadInfo(
                    thread_id=None,
                    name="main",
                    session_id=data.get("session_id"),
                    jsonl_path=data.get("jsonl_path")
                )

        # Load explicit threads
        for tid_str, thread_data in data.get("threads", {}).items():
            tid = None if tid_str == "null" else int(tid_str)
            project.threads[tid] = ThreadInfo(...)
```

### При сохранении (обратная совместимость)

```python
def _save(self):
    for name, p in self.projects.items():
        project_data = {"chat_id": p.chat_id, "cwd": p.cwd}

        # Backward compat: duplicate threads[None] to legacy fields
        if None in p.threads:
            main_thread = p.threads[None]
            project_data["session_id"] = main_thread.session_id
            project_data["jsonl_path"] = main_thread.jsonl_path

        # Save all threads
        project_data["threads"] = {
            str(tid) if tid is not None else "null": {...}
            for tid, t in p.threads.items()
        }
```

## Изменения по файлам

### session_manager.py

1. Удалить legacy поля из ProjectState (или пометить deprecated)
2. Добавить миграцию в `_load_projects()`
3. Добавить backward compat в `_save()`
4. Обновить `should_cleanup_project()` для проверки threads

### bot.py

1. Убрать legacy branch в `on_message()`:
   ```python
   # БЫЛО:
   if thread:
       # multi-thread
   else:
       # legacy

   # СТАЛО:
   thread = project.threads.get(thread_id)
   if not thread:
       thread = create_main_thread() if thread_id is None else create_pending_thread()
   # unified path
   ```

2. Обновить `get_session_for_chat()` → искать в threads[None]

3. Убрать `launch_claude_new()`, использовать `launch_claude_in_thread()` для всех

### history_watcher.py

1. Удалить `poll_for_session()` (legacy)
2. Использовать `poll_for_session_thread()` для всех случаев
3. В `_check_for_changes()`:
   - Итерировать по threads, не по project
   - Для каждого thread проверять его session отдельно

### watcher.py

1. Удалить `watcher_for_session()`
2. Переименовать `watch_thread_jsonl()` → `watch_session()`
3. Унифицировать интерфейс

## Тестирование

### Сценарии для проверки

1. **Private chat:**
   - /start → создаётся threads[None]
   - Сообщения → отправляются в claude-{project}
   - Ответы → приходят без thread_id

2. **Simple group:**
   - /start → создаётся threads[None]
   - Сообщения от разных юзеров → один Claude
   - Ответы → в общий чат

3. **Forum group - только General:**
   - /start в General → threads[None]
   - Работает как Simple group

4. **Forum group - General + Topics:**
   - /start в General → threads[None]
   - /session_new → threads[456] с magic name
   - Сообщения в General → только в General
   - Сообщения в топик → только в топик
   - **НЕТ ДУБЛИРОВАНИЯ**

5. **Forum group - только Topics (без General):**
   - /session_new в топике → threads[456]
   - General пустой (threads[None] не создан)
   - Сообщения в General → предлагают /start

## Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Сломается миграция старых конфигов | Средняя | Тесты + fallback на legacy |
| Производительность scan jsonl | Низкая | Кэширование по mtime |
| Race condition при создании threads | Низкая | Lock или atomic operations |

## Альтернативы рассмотренные

### 1. Просто добавить проверку "сессия занята thread-ом"

```python
# В poll_for_session (legacy)
if is_session_used_by_thread(session_id, project):
    continue  # Пропустить
```

**Минусы:**
- Заплатка, не решает архитектурную проблему
- Два code paths остаются
- Сложнее поддерживать

### 2. Отдельные history.jsonl для каждого thread

**Минусы:**
- Требует изменений в Claude Code (не наш код)
- Не реалистично

### 3. Выбрано: Унификация через threads[None]

**Плюсы:**
- Один code path для всех случаев
- Явная изоляция
- Легко понять и поддерживать
- Backward compatible
