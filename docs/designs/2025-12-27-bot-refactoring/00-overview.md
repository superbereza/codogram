# Bot.py Refactoring Design

## Проблема

`bot.py` — 1273 строки, God Object:
- 6 команд
- ~12 callback-хендлеров
- FSM-состояние через `_start_state` dict
- 2 функции запуска с дублированной анимацией (~100 строк каждая)
- Хелперы (admin check, validation, retry)

**Боли:**
- Сложно добавлять новые команды — непонятно куда класть
- Дублирование кода — анимация запуска повторяется дважды

## Решение

**Архитектура:** Layer-based + Middleware

```
handlers/ → services/ → domain/
              ↓
          adapters/
```

## Финальная структура

```
src/codogram/
├── handlers/
│   ├── __init__.py           # register_handlers()
│   ├── start.py              # /start + callbacks
│   ├── sessions.py           # /session_new, /session_close, etc.
│   ├── permissions.py        # permission Yes/No/Esc
│   ├── messages.py           # on_message routing
│   └── public.py             # /my_chat_id (без admin check)
│
├── services/
│   ├── __init__.py
│   ├── launch.py             # LaunchService
│   ├── project.py            # ProjectService
│   ├── start_flow.py         # StartFlowService
│   ├── message_router.py     # MessageRouterService
│   └── git.py                # GitService
│
├── domain/
│   ├── __init__.py
│   ├── models.py             # ProjectState, ThreadInfo, StartFlowData
│   ├── states.py             # FSM StatesGroup
│   ├── validators.py         # is_valid_project_name
│   └── errors.py             # CodogramError hierarchy
│
├── adapters/
│   ├── __init__.py
│   ├── telegram.py           # send_with_retry, chunking
│   ├── tmux.py               # TmuxAdapter (wrap existing)
│   └── history.py            # HistoryAdapter (wrap existing)
│
├── middleware/
│   ├── __init__.py
│   ├── admin.py              # AdminMiddleware
│   └── dependencies.py       # DI middleware
│
├── keyboards/
│   ├── __init__.py
│   ├── permissions.py
│   ├── start_flow.py
│   └── common.py
│
├── config.py                 # без изменений
├── state.py                  # permission_messages (временно)
├── session_manager.py        # без изменений (пока)
└── main.py                   # wiring
```

## Ключевые решения

| Вопрос | Решение | Почему |
|--------|---------|--------|
| Валидаторы | `domain/validators.py` | Валидация — domain concern |
| FSM | aiogram `StatesGroup` в `domain/states.py` | Встроенное решение, типизация, timeout |
| DI | Middleware injection | Явные зависимости, тестируемость |
| Admin check | `middleware/admin.py` | Убрать boilerplate из каждого handler |

## Принципы

- Handlers знают о Services, но не наоборот
- Services знают о Domain и Adapters
- Domain ни о чём не знает (чистые dataclasses)
- Adapters — обёртки над внешними системами

## Маппинг bot.py → новые файлы

| Строки | Функция | Куда |
|--------|---------|------|
| 41-50 | `get_admin_ids()`, `is_admin()` | middleware/admin.py |
| 52-57 | `is_valid_project_name()` | domain/validators.py |
| 60-84 | `send_with_retry()` | adapters/telegram.py |
| 87-128 | `get_*_for_chat()`, `is_claude_running()` | services/project.py |
| 130-148 | `show_status()` | services/start_flow.py |
| 150-164 | `_make_task_starters()` | services/launch.py |
| 166-257 | `_start_project_flow()`, `_connect_or_launch()` | services/start_flow.py |
| 260-334 | `cmd_start()` | handlers/start.py |
| 336-568 | `launch_claude_new/thread()` | services/launch.py (merge) |
| 571-718 | session_close, session_new | handlers/sessions.py |
| 720-903 | start flow callbacks | handlers/start.py |
| 906-985 | utility commands | handlers/sessions.py |
| 988-1039 | permission callback | handlers/permissions.py |
| 1042-1111 | tmux select, launch, cancel | handlers/start.py |
| 1114-1274 | `on_message()` | handlers/messages.py |

## Экономия

**Было:** 1 файл × 1273 строки
**Стало:** 15+ файлов × 50-180 строк каждый

**Экономия ~400 строк:**
- Удаление дублей анимации (~80 строк)
- Удаление повторных `if not is_admin()` (~40 строк)
- Тонкие handlers вместо логики в них (~200 строк)
