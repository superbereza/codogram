# E2E Test Structure Design

## Overview

Структура для ручных E2E тестов, выполняемых Claude через Telegram MCP.

## Цели

1. Единое место для всех E2E тестов
2. Возможность сказать "прогони smoke/critical/full"
3. Claude полностью автономно выполняет тесты через MCP
4. Структура по командам, не по фичам

## Структура файлов

```
docs/e2e/
├── CLAUDE.md                 # Инструкции для Claude по тестированию
├── suites/
│   ├── smoke.md              # [~2 мин] Продакшн проверка
│   ├── critical.md           # [~15 мин] Основной набор
│   └── full.md               # [~30 мин] Полное покрытие
└── commands/
    ├── start.md              # /start, /restart
    ├── sessions.md           # /new, /clear, /esc, /resume
    ├── threads.md            # /thread
    ├── branches.md           # /branch
    ├── finish.md             # /finish
    ├── settings.md           # /help, /settings, /auto_accept
    ├── permissions.md        # Permission buttons
    ├── watcher.md            # Tool call output
    └── messages.md           # Message forwarding
```

## Формат теста

```markdown
### TC-START-005: Resume session after tmux kill

**Tags:** critical, start, resume
**Preconditions:** Branch topic with bound session, tmux not running

**Setup:**
1. Ensure session_id exists: `cat .config.json | jq '.projects["test"].threads["283"].session_id'`
2. Kill tmux if running: `tmux kill-session -t claude-test-branch 2>/dev/null || true`

**Steps:**
1. `mcp__telegram__reply_to_message(chat_id=TEST_CHAT, message_id=283, text="/start")`
2. `sleep(15)`
3. `mcp__telegram__list_messages(chat_id=TEST_CHAT, reply_to=283, limit=5)`

**Expected:**
- UI: Message contains `[~] Resuming session`
- State: `tmux has-session -t claude-test-branch` returns 0

**Cleanup:** None required
```

### Элементы теста

| Элемент | Описание |
|---------|----------|
| ID | `TC-{COMMAND}-{NNN}` для ссылок из suites |
| Название | Краткое описание теста |
| Tags | smoke/critical/full + категория |
| Preconditions | Что должно быть true перед тестом |
| Setup | Команды для создания preconditions |
| Steps | MCP/bash команды для выполнения |
| Expected | UI (текст) и State (структурные проверки) |
| Cleanup | Опционально, если нужно |

## Формат suite

```markdown
# Critical Test Suite

**Время:** ~15 минут
**Когда:** Перед мержем, после значительных изменений

## Тесты

| ID | Название | Файл |
|----|----------|------|
| TC-START-001 | /start connects to tmux | commands/start.md |
| TC-START-002 | /start launches Claude | commands/start.md |
| ... | ... | ... |

## Запуск

Скажи Claude: "Прогони critical тесты"
```

## Формат CLAUDE.md

```markdown
# E2E Testing Guide

## Как запустить тесты

1. Скажи "прогони smoke тесты" / "прогони critical тесты" / "прогони full тесты"
2. Claude прочитает suite файл и выполнит тесты последовательно
3. После каждого теста Claude сообщит результат

## При нахождении бага

**ВАЖНО:** При обнаружении бага:

1. **Задокументируй подробно** в `docs/bugs/active/YYYY-MM-DD-<краткое-описание>.md`:
   - Шаги воспроизведения
   - Ожидаемый результат
   - Фактический результат
   - Логи, скриншоты, состояние системы

2. **Продолжай тестирование** если баг не блокирует следующие тесты

3. **Если баг блокирует** — отметь какие тесты пропущены и почему

## Тестовое окружение

- **Тестовый чат:** -1003356094635 (codogram-testing-area)
- **Тестовый репозиторий:** /tmp/test-branch-repo
```

## Suites

### Smoke (~5 тестов, ~2 мин)

Продакшн проверка "бот жив?":

| # | Тест |
|---|------|
| 1 | `/help` отвечает |
| 2 | `/start` подключается |
| 3 | Сообщение доходит до Claude |
| 4 | Tool call появляется |
| 5 | Permission кнопки появляются |

### Critical (~21 тест, ~15 мин)

Основной набор для разработки:

| # | Категория | Тест |
|---|-----------|------|
| 1 | Start | `/start` подключается к существующему tmux |
| 2 | Start | `/start` запускает Claude (нет tmux) |
| 3 | Start | `/start` в topic |
| 4 | Resume | `/start` resume в General |
| 5 | Resume | `/start` resume в Topic |
| 6 | Resume | `/start` resume в Branch |
| 7 | Resume | session_id сохраняется при kill tmux |
| 8 | Messages | Сообщение доходит до Claude |
| 9 | Messages | Сообщение изолировано (не в других threads) |
| 10 | Watcher | Tool call появляется в правильном topic |
| 11 | Watcher | Tool call НЕ появляется в других topics |
| 12 | Poller | Permission кнопки в правильном topic |
| 13 | Poller | Permission кнопки НЕ в других topics |
| 14 | Permissions | Клик работает |
| 15 | Permissions | auto_accept работает |
| 16 | Sessions | `/new` создаёт новую сессию |
| 17 | Sessions | `/esc` отменяет запрос |
| 18 | Threads | `/thread` создаёт topic |
| 19 | Branches | `/branch` создаёт worktree + topic |
| 20 | Finish | `/finish` archive topic |
| 21 | Finish | `/finish` merge branch |

### Full (~40+ тестов, ~30 мин)

Всё из Critical плюс:

- `/restart` перезапуск
- `/clear` очистка состояния
- `/resume` явное возобновление
- `/settings`, `/auto_accept`, `/get_debug_ids`
- `/start` edge cases (no dir, git clone, multiple tmux)
- `/finish` все варианты (merge+push, discard)
- Error handling (tmux died, invalid session, deleted worktree)
- Bot restart recovery
- Long messages chunking

## Проверки (Assertions)

### UI проверки
Текстовый матчинг ответа бота:
```python
messages = mcp__telegram__list_messages(chat_id=TEST_CHAT, limit=5)
assert "[~] Resuming session" in messages
```

### State проверки
Структурные проверки config/системы:
```bash
# session_id сохранён
cat .config.json | jq '.projects["test"].threads["283"].session_id' != null

# tmux существует
tmux has-session -t claude-test-branch

# topic закрыт
mcp__telegram__list_topics содержит "Closed: Yes"
```

## Тестовое окружение

- **Тестовый чат:** `-1003356094635` (codogram-testing-area)
- **Тестовый репозиторий:** `/tmp/test-branch-repo`
- Каждый тест самодостаточен (собственный setup)
- Тесты не зависят от порядка выполнения

## Как добавить тест

1. Добавь тест в соответствующий `commands/*.md`
2. Присвой ID: `TC-{COMMAND}-{NNN}`
3. Добавь tags: smoke/critical/full
4. Добавь ID в соответствующий suite

## Миграция

Существующий `docs/tests/2025-01-05-e2e-regression.md` будет перенесён в новую структуру и удалён.
