# Codogram - Claude Runtime Context

## What it does

Telegram bot for managing Claude Code sessions through Telegram:
- Shows permission prompts with Yes/No buttons
- Sends messages to tmux session running Claude
- Monitors tool calls and displays them in Telegram

## Architecture

**Session discovery:** history.jsonl polling (not hooks)
**Refresh interval:** 15s
**Cleanup threshold:** 30 days (by jsonl mtime)

### How sessions are discovered

1. User sends `/start` or `/start <project_name>` in Telegram
2. Bot discovers tmux session by scanning all tmux panes for matching cwd
3. Bot polls `~/.claude/history.jsonl` every 15s to find session_id for that project
4. Bot monitors both tmux (for permission prompts) and jsonl (for tool calls)

### Session lifecycle

- **Registration**: `/start` command discovers tmux + polls for session_id
- **Updates**: history.jsonl polling detects session changes (/new, /resume, /compact)
- **Cleanup**: Projects with jsonl mtime > 30 days are removed

## Key files

```
src/codogram/
├── main.py                   # Bot entry point
├── config.py                 # Settings + config persistence
├── session_manager.py        # ProjectManager - project state
├── telegram_queue.py         # Rate-limited message queue
├── handlers/                 # Telegram command handlers
│   ├── start.py              # /start flow
│   ├── sessions.py           # /new, /clear, /resume
│   ├── threads.py            # /thread_create, /thread_delete
│   ├── branches.py           # /branch_create, /branch_finish
│   └── settings.py           # /settings, /auto_accept, /help
├── services/                 # Business logic
│   ├── start_flow.py         # StartFlowService
│   └── branch.py             # Branch operations
├── middleware/               # Global middleware
│   └── admin.py              # AdminMiddleware
├── history_reader.py         # Parse ~/.claude/history.jsonl
├── permission_poller.py      # Poll tmux for permission prompts
├── watcher.py                # Monitor jsonl for tool calls
├── tmux.py                   # Tmux session interaction
└── screen.py                 # Parse tmux screen content
```

## Usage

### Start bot

```bash
./restart.sh
```

### Register project

```bash
# In Telegram:
/start              # Auto-detect or ask for project name
/start myproject    # Start with specific project
```

### Debugging

```bash
# Check if running
ps aux | grep codogram

# View logs
tail -f logs/codogram.log

# View config
cat .config.json | jq
```

## E2E Testing with Telegram MCP

Claude can test the bot end-to-end using the Telegram MCP integration.

**⚠️ IMPORTANT: Always ask user for test chat ID before E2E testing!**

Never use the production codogram chat. Always confirm: "Which chat should I use for E2E testing?"

### Setup

1. MCP configured in `.mcp.json`:
```json
{
  "mcpServers": {
    "telegram": {
      "type": "stdio",
      "command": "/home/superbereza/dev/telegram-mcp/venv/bin/python",
      "args": ["/home/superbereza/dev/telegram-mcp/main.py"]
    }
  }
}
```

2. Ask user for test chat ID before testing

3. Add MCP user ID to ADMIN_IDS in `.env`

### Feedback loop

```bash
# 1. Make code changes

# 2. Restart bot
./restart.sh

# 3. Ask user for test chat ID, then send command via MCP
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/help")

# 4. Read response
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)

# 5. Check logs if needed
tail -f logs/codogram.log
```

### Available MCP tools

- `mcp__telegram__send_message` - send commands
- `mcp__telegram__get_messages` - read bot responses
- `mcp__telegram__list_inline_buttons` - see keyboard buttons
- `mcp__telegram__press_inline_button` - click buttons

## Constraints

- One Claude per tmux session (split panes not supported)
- cwd is fixed at `/start` (cd commands not tracked)
- Session changes detected within 15s (polling interval)
- Requires tmux session to be running in specified directory

## Deprecated features

- **Hooks**: `hooks/session-start.sh` and `hooks/session-end.sh` do nothing (kept for backwards compat)
- **HTTP server**: Removed in favor of history.jsonl polling
- **settings.json hooks**: No longer needed

## Layered Architecture

Проект использует слоистую архитектуру:

```
src/codogram/
├── handlers/          # Thin routers — принимают Telegram events, делегируют в services
├── services/          # Business logic — start_flow, branch, message_router, launch
├── domain/            # Models, validators, FSM states
├── middleware/        # Global middleware (AdminMiddleware)
├── adapters/          # External integrations (telegram.py)
├── keyboards/         # Inline keyboard builders
└── *.py               # Core modules (tmux, watcher, poller, etc.)
```

**Принципы:**
- Handlers не содержат бизнес-логику — только роутинг
- Services не знают о Telegram API — работают с абстракциями
- Domain models — чистые dataclasses без зависимостей

## Feature Development Flow

При разработке новой фичи придерживаемся следующего процесса:

### 1. Brainstorming → Design
Используем skill `superpowers:brainstorming` для проработки идеи:
- Понимание требований через вопросы
- Рассмотрение 2-3 подходов с trade-offs
- Формирование дизайна по секциям с валидацией
- Результат: `docs/designs/YYYY-MM-DD-<topic>.md`

### 2. Planning → Implementation Plan
Используем skill `superpowers:write-plan` для создания плана:
- Декомпозиция на конкретные задачи
- Учёт layered architecture
- Результат: `docs/plans/YYYY-MM-DD-<topic>-plan.md`

### 3. E2E Tests
Перед/во время реализации прорабатываем E2E тесты:
- Читаем `docs/e2e/CLAUDE.md` для понимания формата
- Добавляем тесты в соответствующие файлы `docs/e2e/commands/`
- Обновляем suites если нужно

### 4. Implementation
- Следуем плану и layered architecture
- Код в соответствующих слоях
- Тесты по ходу

### 5. Completion
После завершения фичи:
- Переносим design в `docs/designs/done/`
- Переносим plan в `docs/plans/done/` (если есть такая папка)
- Актуализируем `docs/ROADMAP.md` и `docs/ROADMAP.ru.md`

## See also

- `docs/setup.md` - Installation and setup guide
- `docs/ONBOARDING.md` - Detailed onboarding for new Claude sessions
- `docs/ROADMAP.md` - Future features and improvements
- `docs/specs/tone-of-voice.md` - Message style guidelines
- `docs/e2e/CLAUDE.md` - E2E testing guide
