# Bot.py Refactoring Design

> **Статус:** План актуализирован 2025-01-03

## Проблема

`bot.py` — **1361 строка** (было 1273), God Object:
- 10 команд: `/start`, `/thread_create`, `/thread_delete`, `/get_debug_ids`, `/esc`, `/resume`, `/new`, `/clear`, `/restart`
- ~15 callback-хендлеров
- FSM-состояние через `_start_state` dict
- Хелперы (admin check, validation, retry, task starters)

**Боли:**
- Сложно добавлять новые команды — непонятно куда класть
- Повторяющийся код запуска анимации в callback'ах (~6 мест)

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
│   ├── threads.py            # /thread_create, /thread_delete
│   ├── sessions.py           # /new, /clear, /restart, /esc, /resume, /get_debug_ids
│   ├── permissions.py        # permission Yes/No/Esc
│   └── messages.py           # on_message routing
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
| Admin check | `middleware/admin.py` на **Dispatcher** | Глобальная защита ВСЕХ роутеров. Не-админы получают свой ID автоматически |
| /my_chat_id | Переименован в `/get_debug_ids` | Только для админов. Не-админы получают ID из middleware rejection |

## Принципы

- Handlers знают о Services, но не наоборот
- Services знают о Domain и Adapters
- Domain ни о чём не знает (чистые dataclasses)
- Adapters — обёртки над внешними системами

## Маппинг bot.py → новые файлы (актуализирован 2025-12-30)

| Строки | Функция | Куда |
|--------|---------|------|
| 41-50 | `get_admin_ids()`, `is_admin()` | middleware/admin.py |
| 52-57 | `is_valid_project_name()` | domain/validators.py |
| 60-84 | `send_with_retry()` | adapters/telegram.py (или telegram_queue.py) |
| 87-139 | `get_*_for_chat()`, `is_claude_running()` | services/project.py |
| 141-159 | `show_status()` | services/start_flow.py |
| 161-177 | `_make_task_starters()` | services/launch.py |
| 179-289 | `_start_project_flow()`, `_start_thread_flow()`, `_connect_or_launch()` | services/start_flow.py |
| 292-393 | `cmd_start()` | handlers/start.py |
| 396-428 | `launch_claude_in_thread()` | services/launch.py (использует launch_animation.py) |
| 431-577 | `/thread_delete`, `/thread_create` + callbacks | handlers/threads.py |
| 580-808 | start flow callbacks (git, clone, etc.) | handlers/start.py |
| 811-814 | `/get_debug_ids` (бывший /my_chat_id) | handlers/sessions.py |
| 816-823 | `/esc` | handlers/sessions.py |
| 826-843 | `/resume` | handlers/sessions.py |
| 846-898 | `_send_session_command()`, `/new`, `/clear` | handlers/sessions.py |
| 901-1039 | `/restart` + callbacks | handlers/sessions.py |
| 1042-1093 | permission callback | handlers/permissions.py |
| 1096-1130 | tmux select callback | handlers/start.py |
| 1133-1184 | launch_claude, cancel callbacks | handlers/start.py |
| 1187-1361 | `on_message()` | handlers/messages.py |

## Экономия

**Было:** 1 файл × 1361 строка
**Стало:** 14+ файлов × 50-180 строк каждый

**Ожидаемая экономия ~350 строк:**
- Удаление дублей launch_with_animation вызовов (~60 строк, 6 мест)
- Удаление повторных `if not is_admin()` (~45 строк, ~15 мест)
- Тонкие handlers вместо логики в них (~200 строк)
- DRY в FSM через aiogram StatesGroup (~50 строк)

## Уже вынесено (частично готово)

| Модуль | Что делает | Статус |
|--------|------------|--------|
| `telegram_queue.py` | Rate limiting, batching, retry | ✅ Готово |
| `launch_animation.py` | FACES, анимация, создание tmux | ✅ Готово |
| `keyboards.py` | Клавиатуры (частично) | ⚠️ Частично |
| `start_flow.py` | Keyboard builders для start flow | ⚠️ Только keyboards |

## Дополнительный техдолг (выявлен 2025-12-30)

### Критичное дублирование

| Файл | Проблема | Решение |
|------|----------|---------|
| `permission_poller.py:31-367` | 2 функции по ~170 строк почти идентичны (project vs thread) | Унифицировать в одну с параметром |
| `bot.py` | launch_with_animation повторяется 6 раз | services/launch.py — единая точка |

### Hardcoded значения → config.py

| Файл:строка | Константа | Значение |
|-------------|-----------|----------|
| `history_watcher.py:16` | REFRESH_INTERVAL | 15 сек |
| `history_watcher.py:238` | BINDING_TIMEOUT | 300 сек |
| `launch_animation.py:104` | LAUNCH_TIMEOUT | 120 сек |
| `session_manager.py:79` | CLEANUP_DAYS | 30 дней |
| `permission_poller.py` | DEBOUNCE_TIME | 0.5 сек (дублируется!) |

### Архитектурные костыли

| Файл | Проблема | Решение |
|------|----------|---------|
| `main.py:4-7` | Hack с sys.modules для circular import | DI в Фазе 11 решит |
| `tmux.py:39-71` | Блокирующие time.sleep() между send-keys | adapters/tmux.py с async |
| `tmux.py:10-11` | mkdir при импорте модуля | Lazy init в adapters/ |
| `history_watcher.py:262` | hash() вместо UUID для msg_id | domain/models.py — proper ID |

### Нарушение SRP

| Файл | Проблема | Решение |
|------|----------|---------|
| `session_manager.py:13-79` | should_cleanup_project смешивает legacy и новую логику | services/cleanup.py |
| `history_watcher.py:55-123` | _check_for_changes делает слишком много | Разбить на отдельные services |

### Неиспользуемый код

| Файл | Что | Действие |
|------|-----|----------|
| `watcher.py:29-51` | find_missed_entries не вызывается | Удалить в Фазе 11 |
| `session_manager.py:121-133` | 8 DEPRECATED полей | Удалить после миграции на threads |
