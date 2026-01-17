# Codogram Onboarding

Документ для быстрого онбординга новой сессии Claude.

## Что это

Codogram — Telegram бот для управления Claude Code:
- Показывает permission prompts (кнопки Yes/No)
- Отправляет сообщения в tmux сессию Claude
- Следит за jsonl и показывает tool calls

## Архитектура

```
Claude Code                    Codogram                     Telegram
    │                              │                              │
    │                         history.jsonl                       │
    │                         polling (15s)                       │
    │                              │                              │
    │                         ProjectManager                      │
    │                              │                              │
    │                         ┌────┴────┐                         │
    │                         │         │                         │
    │ ◄──── tmux ◄──── Permission    Watcher ─────────────────────►│
    │                   Poller       (jsonl)                       │
    │                         │         │                         │
    │                         └────┬────┘                         │
    │                              │                              │
    │                         ThreadInfo                          │
    │                    (multi-session topics)                   │
```

**Session discovery:** history.jsonl polling (не hooks)
**Refresh interval:** 15s
**Cleanup threshold:** 30 days (по mtime jsonl)

## Ключевые файлы

```
codogram/
├── .env                      # TELEGRAM_TOKEN, ADMIN_IDS
├── .config.json              # Projects + chat mapping (auto-created)
├── src/codogram/
│   ├── main.py               # Bot entry point
│   ├── config.py             # Settings + config persistence
│   ├── session_manager.py    # ProjectManager - project state
│   ├── history_reader.py     # Parse ~/.claude/history.jsonl
│   ├── history_watcher.py    # Monitor history.jsonl for session changes
│   ├── permission_poller.py  # Poll tmux for permission prompts
│   ├── watcher.py            # Monitor session jsonl for tool calls
│   ├── handlers/             # Telegram command handlers (8 modules)
│   ├── services/             # Business logic (launch, branch, message_router)
│   ├── middleware/           # Admin check middleware
│   ├── tmux.py               # Tmux session interaction
│   └── screen.py             # Parse tmux screen content
└── stop-and-restart.sh       # Restart bot script
```

## Как дебажить

### Логи

```bash
# Что отправлено в Telegram
tail -f ~/dev/personal-agent/tmp/codogram-logs/poller-sent.log

# State machine поллера
tail -f ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log
```

### Проверить что бот запущен

```bash
ps aux | grep codogram
```

### Перезапустить бота

```bash
./stop-and-restart.sh
```

### Проверить конфиг

```bash
cat .config.json | jq
```

## Типичные проблемы

### Бот не отвечает

1. Проверить запущен ли: `ps aux | grep codogram`
2. Проверить логи: `tail -20 ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log`
3. Перезапустить: `./stop-and-restart.sh`

### Permission prompts не появляются

1. Проверить что проект зарегистрирован: `cat .config.json | jq '.projects'`
2. Проверить что tmux сессия найдена
3. Подождать до 15s (polling interval)

### Сообщения не доходят до tmux

1. **Бот должен быть админом группы** (Privacy Mode в Telegram)
2. Проверить что tmux сессия жива: `tmux ls`
3. Проверить chat_id в конфиге

## Команды для разработки

```bash
# Активировать venv
source ~/dev/codogram/venv/bin/activate

# Запустить тесты
python -m pytest tests/ -v

# Перезапустить бота
./stop-and-restart.sh

# Git log
git log --oneline -10
```

## Документация

- `CLAUDE.md` — runtime context для Claude
- `docs/setup.md` — установка и настройка
- `docs/ROADMAP.md` — roadmap и backlog
- `docs/designs/` — design documents
- `docs/plans/` — implementation plans
