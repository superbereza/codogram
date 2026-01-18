# E2E Testing Guide

Руководство для Claude по выполнению E2E тестов через Telegram MCP.

## Как запустить тесты

1. **Уточни тестовый чат** — спроси пользователя в каком чате тестировать (по умолчанию: codogram-testing-area)
2. Прочитай соответствующий suite файл из `suites/`
3. Выполняй тесты последовательно, сообщая результат каждого

## Тестовое окружение

- **Тестовый чат:** `-1003356094635` (codogram-testing-area)
- **Тестовый репозиторий:** `/tmp/test-branch-repo`
- Бот должен быть запущен: `./stop-and-restart.sh`

## Выполнение теста

Для каждого теста:

1. **Setup** — выполни команды подготовки
2. **Steps** — выполни MCP команды
3. **Expected** — проверь UI (текст ответа) и State (config/tmux)
4. **Cleanup** — выполни если указано
5. **Результат** — PASS / FAIL с деталями

### Гибридные тесты (ASK USER)

Некоторые тесты требуют наблюдения пользователя (динамические UI элементы, которые MCP не видит).

**Паттерн ASK USER:**
```
Steps:
1. mcp__telegram__send_message(...)
2. **ASK USER:** "Видишь X в Telegram?"
3. User отвечает да/нет
4. Продолжаем или фейлим тест
```

**Как выполнять:**
1. Выполни MCP команды до ASK USER
2. Задай вопрос пользователю и жди ответа
3. На основе ответа определи PASS/FAIL
4. Продолжи со следующим шагом

**Результаты:**
- **PASS** — user подтвердил ожидаемое поведение
- **FAIL** — user не подтвердил
- **SKIP** — тест невозможно выполнить (например, Claude не выдал саджест)

### Пример выполнения

```
TC-START-001: /start connects to existing tmux
Setup: tmux new-session -d -s claude-codogram-testing-area
Steps: mcp__telegram__send_message(chat_id=-1003356094635, message="/start")
Expected: Response contains "Connected to claude-codogram-testing-area"
Result: PASS
```

## При нахождении бага

**ВАЖНО:** При обнаружении бага:

1. **Задокументируй подробно** в `docs/bugs/active/YYYY-MM-DD-<краткое-описание>.md`:
   - Шаги воспроизведения (точные MCP команды)
   - Ожидаемый результат
   - Фактический результат
   - Логи (`tail -50 logs/codogram.log`)
   - Состояние config (`.config.json`)
   - Состояние tmux (`tmux list-sessions`)

2. **Продолжай тестирование** если баг не блокирует следующие тесты

3. **Если баг блокирует** — отметь какие тесты пропущены и почему

### Формат bug report

```markdown
# [Краткое описание]

**Найден в тесте:** TC-XXX-NNN
**Severity:** critical/major/minor
**Status:** active

## Воспроизведение

1. [Шаг 1]
2. [Шаг 2]

## Ожидаемый результат

[Что должно было произойти]

## Фактический результат

[Что произошло на самом деле]

## Логи

\`\`\`
[Релевантные строки из logs/codogram.log]
\`\`\`

## Дополнительный контекст

[config.json, tmux state, etc.]
```

## MCP команды

```python
# Отправить команду
mcp__telegram__send_message(chat_id=-1003356094635, message="/help")

# Отправить в topic (через reply)
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TOPIC_MSG_ID, text="/start")

# Прочитать ответы
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=TOPIC_MSG_ID, limit=5)

# Проверить inline кнопки
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)

# Нажать кнопку
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Yes")
```

## Структура файлов

```
docs/e2e/
├── CLAUDE.md           # Это руководство
├── suites/
│   ├── smoke.md        # [~2 мин] Продакшн проверка
│   ├── critical.md     # [~25 мин] Основной набор
│   └── full.md         # [~40 мин] Полное покрытие
└── commands/
    ├── setup.md        # Setup flow v2 (onboarding)
    ├── start.md        # /start, /restart (existing project)
    ├── sessions.md     # /new, /clear, /esc, /resume
    ├── threads.md      # /thread
    ├── branches.md     # /branch
    ├── finish.md       # /finish
    ├── settings.md     # /help, /settings, /auto_accept
    ├── permissions.md  # Permission buttons
    ├── watcher.md      # Tool call output
    ├── messages.md     # Message forwarding
    └── activity.md     # Thinking status, suggestions (ASK USER)
```
