# Code Cleanup Plan — Phase 1

**Date:** 2026-01-18
**Status:** ✅ Complete (Phase 1)
**Completed:** 2026-01-20

## Overview

Цель: уменьшить технический долг, улучшить maintainability и тестируемость.

Подход: разбивка по уровню риска. Сначала безопасные изменения, потом более рискованные.

| Фаза | Риск | Scope | Статус |
|------|------|-------|--------|
| Phase 1 | Low | Circular dependency, magic numbers | ✅ Done |
| Phase 2 | Medium | @require_state() decorator | → Отдельная задача |
| Phase 3 | High | LaunchService, DEPRECATED fields, ThreadInfo | → Отдельная задача |

Принцип: каждая фаза — атомарная. Можно остановиться после любой фазы и код останется рабочим.

## Resolution

**Phase 1 завершён.** Выполнено:
- Circular dependency fix в `handlers/messages.py`
- Magic numbers вынесены в константы

**Phase 2-3 не реализованы** — решено делать в рамках отдельного процесса рефакторинга:
- Phase 2: `@require_state()` decorator
- Phase 3: LaunchService + DEPRECATED fields + ThreadInfo refactoring

---

## Phase 1 — Quick Wins (Low Risk)

### Задача 1.1: Circular Dependency Fix

**Проблема:** `handlers/messages.py` импортирует `main.telegram_queue` напрямую:
```python
from .. import main
# ...
main.telegram_queue
```

**Решение:** использовать aiogram DI — `telegram_queue` уже зарегистрирован в `main.py`:
```python
dp["telegram_queue"] = telegram_queue
```

**Изменения:**
- `handlers/messages.py` — убрать `from .. import main`, брать из `data["telegram_queue"]`

### Задача 1.2: Magic Numbers → Constants

Вынести магические числа в константы:
- `screen.py:258` — `'─' * 10`
- `telegram_queue.py:274` — `4000` (Telegram message limit)
- `history_watcher.py` — tmux capture-pane `-S -30`

**Решение:** добавить константы в `config.py`.

**Оценка:** ~15-20 минут на обе задачи.

---

## Phase 2 — Medium Risk (Backlog)

### Задача 2.1: @require_state() Decorator

**Проблема:** 15+ callback handlers в `start.py` с одинаковым паттерном валидации состояния.

**Решение:** декоратор
```python
@require_state(ResetFlow.awaiting_choice, fields=["project_name"])
async def on_reset_keep(callback, state, data):
    # только бизнес-логика
```

**Сложности:**
- Разные handlers требуют разные поля
- Нужно поддержать и Message, и CallbackQuery
- Тесты на edge cases

---

## Phase 3 — High Risk (Backlog)

### Задача 3.1: LaunchService

Вынести `_launch_claude_in_thread()` (113 строк) из handler в service. Требует дизайна интерфейса и error handling.

### Задача 3.2: DEPRECATED Fields Removal

Удалить 8 legacy полей из `ProjectState`:
- session_id
- jsonl_path
- watcher_task
- tmux_session
- poller_task
- last_sent_message
- binding_task
- awaiting_new_session

Требует аудита использований и миграции конфига.

### Задача 3.3: ThreadInfo Refactoring

Разбить 20+ полей на композиции:
- `ThreadIdentity` (thread_id, name, topic_name)
- `ClaudeSession` (session_id, jsonl_path)
- `ThreadTasks` (watcher_task, poller_task, binding_task, launch_task)

Архитектурное изменение, много затронутого кода.
