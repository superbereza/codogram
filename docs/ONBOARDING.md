# Telegram Bridge Onboarding

Документ для быстрого онбординга новой сессии Claude на продолжение разработки/дебага.

## Что это

Telegram-bridge — бот для управления Claude Code через Telegram:
- Показывает permission prompts (кнопки Yes/No)
- Отправляет сообщения в tmux сессию Claude
- Следит за jsonl и показывает tool calls

## Текущий статус (2025-12-24)

**Только что имплементировано:** Multi-session architecture

- Один процесс бота обслуживает несколько Claude сессий
- Сессии регистрируются через Claude Code hooks (SessionStart/SessionEnd)
- Каждый проект = отдельная Telegram группа
- Маппинг project_name → chat_id

**Ещё не протестировано:** интеграционный тест после рефакторинга.

## Ключевые файлы

```
agent-tools/codogram/
├── .env                      # TELEGRAM_TOKEN, ADMIN_CHAT_ID, BASE_DIR
├── .config.json              # projects + sessions mapping (создаётся автоматически)
├── hooks/
│   ├── session-start.sh      # POST /session/register при старте Claude
│   └── session-end.sh        # POST /session/unregister при завершении
├── src/codogram/
│   ├── main.py               # HTTP server :8787 + Telegram bot
│   ├── config.py             # Settings + load/save .config.json
│   ├── session_manager.py    # SessionManager - регистрация, персистенция
│   ├── project_resolver.py   # get_project_name (worktree support)
│   ├── permission_poller.py  # Поллит tmux, отправляет permission prompts
│   ├── watcher.py            # Следит за jsonl, отправляет tool calls
│   ├── bot.py                # Telegram handlers, роутинг по chat_id
│   ├── screen.py             # Парсинг tmux экрана
│   └── tmux.py               # TmuxSession class
└── restart.sh                # Перезапуск бота
```

## Архитектура

```
Claude Code                    codogram                 Telegram
    │                               │                              │
    │ SessionStart hook ──────────► HTTP :8787                     │
    │                               │                              │
    │                          SessionManager                      │
    │                          register_session()                  │
    │                               │                              │
    │                          ┌────┴────┐                         │
    │                          │         │                         │
    │ ◄──── tmux ◄──── Permission    Watcher ─────────────────────►│
    │                   Poller       (jsonl)                       │
    │                          │         │                         │
    │                          └────┬────┘                         │
    │                               │                              │
    │ SessionEnd hook ────────────► unregister_session()           │
```

## Как дебажить

### Логи

```bash
# Что отправлено в Telegram
tail -f ~/dev/personal-agent/tmp/codogram-logs/poller-sent.log

# State machine поллера
tail -f ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log

# Сырой экран tmux
cat ~/dev/personal-agent/tmp/codogram-logs/poller-screen-raw.txt
```

### Проверить что бот запущен

```bash
ps aux | grep codogram
```

### Убить все инстансы и перезапустить

```bash
pkill -f "codogram"
./agent-tools/codogram/restart.sh
```

### Проверить HTTP server

```bash
curl -X POST http://localhost:8787/session/register \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "cwd": "/tmp", "tmux_session": "test"}'
```

### Проверить hooks

```bash
# Должен быть в ~/.claude/settings.json
cat ~/.claude/settings.json | jq '.hooks'
```

### Проверить .config.json

```bash
cat agent-tools/codogram/.config.json
```

## Типичные проблемы

### Бот не отвечает

1. Проверить запущен ли: `ps aux | grep codogram`
2. Проверить логи: `tail -20 ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log`
3. Перезапустить: `./restart.sh`

### Permission prompts не появляются в Telegram

1. Проверить что сессия зарегистрирована: `cat .config.json | jq '.sessions'`
2. Проверить маппинг project → chat: `cat .config.json | jq '.projects'`
3. Проверить что chat_id правильный
4. Проверить поллер логи: `tail -f poller-debug.log`

### Сообщения из Telegram не доходят до tmux

1. **Бот должен быть админом группы** (Privacy Mode в Telegram)
2. Проверить что сессия зарегистрирована с правильным chat_id
3. После компакта session_id меняется — нужна перерегистрация

### Hook не срабатывает

1. Проверить что hook исполняемый: `ls -la hooks/`
2. Проверить что jq установлен: `which jq`
3. Проверить что HTTP server запущен: `curl localhost:8787/session/register`

### Ошибка "No module named..."

```bash
cd agent-tools/codogram
source ../../venv/bin/activate
pip install -e .
```

## Дизайн документы

- `docs/designs/2025-12-24-multi-session-architecture.md` — полный дизайн
- `docs/plans/2025-12-24-multi-session-implementation.md` — план имплементации
- `docs/plans/2025-12-24-telegram-display-samples.md` — примеры отображения для улучшения UI

## Roadmap

См. `ROADMAP.md`:
- Multi-session in one chat (worktree support)
- Activity indicators
- Tool results formatting
- Hidden tools filtering
- Bot command menu
- Self-hosting exception

## Команды для разработки

```bash
# Активировать venv
source ~/dev/personal-agent/venv/bin/activate

# Запустить тесты
cd agent-tools/codogram
python -m pytest tests/ -v

# Перезапустить бота
./restart.sh

# Посмотреть git log
git log --oneline -10
```
