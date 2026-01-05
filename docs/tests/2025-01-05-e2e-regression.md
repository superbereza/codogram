# E2E Regression Test Plan

**Date:** 2025-01-05
**Branch:** refactor-bot (Unified Message Queue migration)
**Test chat:** -1003356094635 (codogram-testing-area)

## Overview

Full regression test after major refactoring:
- TelegramQueue migration (all handlers/services)
- aiogram 3.x Dependency Injection
- tmux exact matching fix (`=` prefix)
- auto_accept dynamic reading fix
- Thread isolation fixes

## Test Matrix

### Контексты

| Контекст | thread_id | tmux naming | Config key |
|----------|-----------|-------------|------------|
| Private/Simple chat | None | `claude-{project}` | - |
| Forum General | None | `claude-{project}` | threads[None] |
| Forum Topic | int | `claude-{project}-{name}` | threads[id] |

### Команды (14)

| Handler | Commands | Callbacks |
|---------|----------|-----------|
| settings.py | /help, /settings, /get_debug_ids, /auto_accept | - |
| start.py | /start, /restart | create_dir, custom_path, git_*, select_tmux:*, restart:* |
| sessions.py | /new, /clear, /esc, /resume | - |
| threads.py | /thread_create, /thread_delete | thread_create_confirm, thread_delete:* |
| branches.py | /branch_create, /branch_finish | bc_*, bf_* |
| permissions.py | - | perm:{option}:{tmux} |
| messages.py | (text messages) | - |

---

## Этап 1 — Smoke (~8 тестов, 5 мин)

Минимум чтобы убедиться что бот работает.

### 1.1 Базовые команды

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| S1 | Any | /help | Показывает список команд | |
| S2 | Any | /settings | Показывает project name, auto-accept status | |
| S3 | Any | /get_debug_ids | Показывает user_id, chat_id, thread_id | |

### 1.2 Подключение к Claude

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| S4 | General | /start (tmux существует) | "Connected to claude-{project}" | |
| S5 | Topic | /start (tmux существует) | "Connected to claude-{project}-{name}" | |
| S6 | Topic | Отправить сообщение | Появляется в tmux | |

### 1.3 Permission & Auto-accept

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| S7 | Any | Permission prompt в Claude | Кнопки появляются в Telegram | |
| S8 | Any | /auto_accept toggle + permission | Автонажатие работает без рестарта | |

---

## Этап 2 — Critical Paths (~15 тестов, 15 мин)

Основные user journeys + регрессии известных багов.

### 2.1 Изоляция (регрессии)

| ID | Тест | Регрессия для | Expected | Status |
|----|------|---------------|----------|--------|
| C1 | tmux exact match | tmux prefix bug | `claude-codogram` НЕ матчит `claude-codogram-immortal` | |
| C2 | Poller isolation | thread-session-mixup | Permission в Topic X → кнопки ТОЛЬКО в Topic X | |
| C3 | Session isolation | session-binding-race | Новая сессия в General не ломает Topic | |
| C4 | /auto_accept General vs Topic | - | Разные флаги, независимые | |

### 2.2 /start сценарии

| ID | Контекст | Сценарий | Expected | Status |
|----|----------|----------|----------|--------|
| C5 | Any | Директория не существует | Create flow → git setup options | |
| C6 | Any | tmux не существует | Launch Claude → animation → Connected | |
| C7 | General | /start | Ищет только `claude-{project}`, НЕ все tmux | |
| C8 | Topic | /start новый тред | Создаёт `claude-{project}-{name}` | |

### 2.3 Session management

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| C9 | Any | /new | Новая сессия, awaiting_new_session=true | |
| C10 | Any | /restart | Kill tmux → предложить перезапуск | |
| C11 | Any | Session binding | Первое сообщение → binds session по user message | |
| C12 | Any | start_requested_at filter | Не биндит сессии созданные ДО /start | |

### 2.4 History Watcher

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| C13 | Any | Tool call в Claude | Tool output появляется в Telegram | |
| C14 | Topic | Tool call в Topic X | Output ТОЛЬКО в Topic X | |
| C15 | Any | Long tool output (>4096) | Разбивается на chunks | |

---

## Этап 3 — Full Coverage (~20 тестов, 30 мин)

Полное покрытие всех команд и edge cases.

### 3.1 Thread Management

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| F1 | General | /thread_create mythread | Создаёт topic + threads[id] | |
| F2 | Topic | /thread_delete | Удаляет topic + config | |
| F3 | Topic | /start в pending thread | Upgrade pending → full thread | |

### 3.2 Branch/Worktree

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| F4 | General | /branch_create feature-x | Создаёт worktree + topic | |
| F5 | Topic | /branch_finish | Merge → cleanup worktree + topic | |

### 3.3 /start Edge Cases

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| F6 | Any | Несколько tmux в cwd | Показывает выбор | |
| F7 | Any | start:custom_path flow | Ввод пути → validation → launch | |
| F8 | Any | start:git_clone flow | Ввод URL → clone → launch | |
| F9 | Topic | /start в незарегистрированном топике | Регистрирует + запускает | |

### 3.4 Session Commands

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| F10 | Any | /clear | Очищает сессию, awaiting_new_session | |
| F11 | Any | /esc | Отправляет Escape в tmux | |
| F12 | Any | /resume (если есть) | Возобновляет сессию | |

### 3.5 Error Handling

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| F13 | Any | tmux died (kill -9) | "Claude crashed" notification | |
| F14 | Any | /start с missing cwd | Graceful error message | |
| F15 | Any | /settings без проекта | "No project. Use /start first." | |

### 3.6 Bot Lifecycle

| ID | Контекст | Тест | Expected | Status |
|----|----------|------|----------|--------|
| F16 | Any | Bot restart | Восстанавливает poller/watcher для активных сессий | |
| F17 | Any | Config persistence | /auto_accept → restart bot → setting preserved | |

### 3.7 Callbacks

| ID | Тест | Expected | Status |
|----|------|----------|--------|
| F18 | cancel button | Отменяет текущий flow | |
| F19 | restart:confirm | Перезапускает Claude | |
| F20 | select_tmux:{name} | Подключается к выбранному | |

---

## Test Setup

### Prerequisites

```bash
# 1. Bot running from worktree
cd /home/superbereza/dev/codogram/.worktrees/refactor-bot
./restart.sh

# 2. Create test tmux for smoke tests
tmux new-session -d -s claude-codogram-testing-area -c /tmp
tmux send-keys -t claude-codogram-testing-area "claude" Enter

# 3. Monitor logs
tail -f logs/codogram.log
```

### MCP Commands

```python
# Send command
mcp__telegram__send_message(chat_id=-1003356094635, message="/help")

# Read response
mcp__telegram__get_messages(chat_id=-1003356094635, page_size=5)

# Check inline buttons
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)

# Press button
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Yes")

# Send to topic (via reply)
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TOPIC_MSG_ID, text="message")
```

---

## Success Criteria

- **Этап 1:** Все 8 тестов pass → бот работает
- **Этап 2:** Все 15 тестов pass → основной функционал OK, регрессий нет
- **Этап 3:** Все 20 тестов pass → полное покрытие

## Known Limitations

- MCP не может отправлять в конкретный topic напрямую (нужен reply_to_message)
- Permission tests требуют реального Claude с permission prompt
- Некоторые тесты требуют ручной верификации tmux содержимого

## References

- `docs/specs/start-scenarios-coverage.md` — матрица /start сценариев
- `docs/specs/start-scenarios-matrix.md` — переменные среды
- `docs/architecture/multi-session.md` — архитектура тредов
- `docs/designs/2025-01-04-unified-message-queue.md` — TelegramQueue design
- `docs/bugs/fixed/` — известные баги и фиксы
