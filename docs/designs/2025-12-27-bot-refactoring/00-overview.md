# Bot.py Refactoring Design

> **Статус:** Актуализировано 2025-01-04. Фазы 1-10 завершены, bot.py удалён.

## Проблема

`bot.py` — **1802 строки** (вырос из-за auto-accept), God Object:
- 15 команд: `/start`, `/thread_create`, `/thread_delete`, `/branch_create`, `/branch_finish`, `/get_debug_ids`, `/esc`, `/resume`, `/new`, `/clear`, `/restart`, `/settings`, `/auto_accept`, `/help`
- 38 router decorators, 47 async functions
- FSM-состояние через `_start_state` dict
- Хелперы (validation, retry, task starters)

**Боли:**
- Сложно добавлять новые команды — непонятно куда класть
- Повторяющийся код запуска анимации в callback'ах (~6 мест)

## Прогресс

| Фаза | Статус | Описание |
|------|--------|----------|
| 1-3 | ✅ Done | Структура папок, domain/, adapters/ |
| 4-6 | ✅ Done | middleware/admin.py, handlers/permissions.py, keyboards/ |
| 7-9 | ✅ Done | FSM в handlers/start.py, все handlers извлечены |
| 10 | ✅ Done | bot.py удалён (522 → 0 строк) |
| 11 | 📋 Planned | Cleanup техдолга (см. 05-phase-11-cleanup.md) |

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
│   ├── start.py              # /start + git callbacks
│   ├── threads.py            # /thread_create, /thread_delete
│   ├── branches.py           # /branch_create, /branch_finish (NEW)
│   ├── sessions.py           # /new, /clear, /restart, /esc, /resume
│   ├── settings.py           # /settings, /auto_accept, /help, /get_debug_ids (NEW)
│   ├── permissions.py        # permission Yes/No/Esc ✅ DONE
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
│   ├── __init__.py           # ✅ DONE
│   ├── admin.py              # AdminMiddleware ✅ DONE
│   └── dependencies.py       # DI middleware
│
├── keyboards/
│   ├── __init__.py           # ✅ DONE
│   ├── permissions.py        # ✅ DONE (migrated from keyboards.py)
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

## Маппинг bot.py → новые файлы (актуализирован 2025-01-03)

> **Note:** Номера строк изменились после merge с main (auto-accept).
> Текущий bot.py: **1802 строки**, 38 decorators, 47 async functions.

| Область | Функции | Куда | Статус |
|---------|---------|------|--------|
| Admin check | `is_admin()`, `get_admin_ids()` | middleware/admin.py | ✅ DONE |
| Validation | `is_valid_project_name()` | domain/validators.py | ✅ DONE |
| Rate limit | `send_with_retry()` | telegram_queue.py | ✅ DONE |
| Helpers | `get_*_for_chat()`, `is_claude_running()` | services/project.py | ⏳ |
| Status | `show_status()` | services/start_flow.py | ⏳ |
| Task starters | `_make_task_starters()` | services/launch.py | ⏳ |
| Start flow | `_start_project_flow()`, `_connect_or_launch()` | services/start_flow.py | ⏳ |
| `/start` | cmd_start + git callbacks (~500 LOC) | handlers/start.py | ⏳ |
| Launch | `launch_claude_in_thread()` | services/launch.py | ⏳ |
| Threads | `/thread_create`, `/thread_delete` + callbacks | handlers/threads.py | ⏳ |
| Branches | `/branch_create`, `/branch_finish` + callbacks (~400 LOC) | handlers/branches.py | ⏳ |
| Settings | `/settings`, `/auto_accept`, `/help`, `/get_debug_ids` | handlers/settings.py | ⏳ |
| Sessions | `/new`, `/clear`, `/restart`, `/esc`, `/resume` | handlers/sessions.py | ⏳ |
| Permissions | perm: callback | handlers/permissions.py | ✅ DONE |
| Tmux select | select_tmux: callback | handlers/start.py | ⏳ |
| Message routing | `on_message()` (~175 LOC) | handlers/messages.py | ⏳ |

## Экономия

**Было:** 1 файл × 1802 строки (после merge auto-accept)
**Станет:** 15+ файлов × 50-180 строк каждый

**Уже достигнуто (Фазы 1-6):**
- ✅ Удалены 30 `if not is_admin()` checks (~90 строк)
- ✅ Permission callback вынесен (handlers/permissions.py)
- ✅ keyboards.py → keyboards/ directory

**Ожидаемая экономия (Фазы 7-11):**
- Удаление дублей launch_with_animation вызовов (~60 строк, 6 мест)
- Тонкие handlers вместо логики в них (~200 строк)
- DRY в FSM через aiogram StatesGroup (~50 строк)

## Уже вынесено

| Модуль | Что делает | Статус |
|--------|------------|--------|
| `telegram_queue.py` | Rate limiting, batching, retry, chunking | ✅ Готово |
| `launch_animation.py` | FACES, анимация, создание tmux | ✅ Готово |
| `middleware/admin.py` | AdminMiddleware на Dispatcher | ✅ Готово |
| `handlers/permissions.py` | Yes/No/Esc buttons | ✅ Готово |
| `keyboards/` | Migrated from keyboards.py | ✅ Готово |
| `domain/` | validators, models, states, errors | ✅ Готово |
| `adapters/telegram.py` | send_with_retry | ✅ Готово |
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
