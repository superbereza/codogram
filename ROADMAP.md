# Telegram Bridge Roadmap

## Done

### Core
- tmux send-keys для input
- jsonl watch для output
- Chunking (4000 символов)
- Статус символы (●◐✓)

### Multi-session architecture
- Один процесс бота на несколько Claude сессий
- Регистрация через Claude Code hooks (SessionStart/SessionEnd)
- HTTP API для регистрации сессий
- Project → Chat mapping
- Git worktree support (резолвит project name)

### Permission handling
- Background poller для permission prompts
- Парсинг контента из tmux capture-pane
- Inline keyboard с опциями
- Удаление сообщений после ответа

### Multi-admin support
- ADMIN_IDS через запятую в .env
- /my_chat_id команда для всех

### Bot command menu
- /start, /my_chat_id, /register_dir, /esc в меню Telegram

## Backlog

### Voice → Whisper
Голосовые сообщения через Whisper transcription:
- Используем существующий код из bz-merch-assistant
- `ai_bot_core/services/whisper.py`

### One chat — multi sessions management
Управление несколькими сессиями в одном проекте:
- Spawn: запустить дополнительную сессию (worktree)
- Change: переключиться на другую сессию
- Resume: `--resume` для продолжения предыдущей
- UI: команды или inline кнопки для переключения

### Activity indicators
Отображение что Claude думает/работает:
- "thinking..." когда Claude обрабатывает
- Throbber/typing indicator
- Слова типа "Hmm", "Let me think"

### Compacting indicator
Отображение процесса компактинга контекста:
- Детектить compacting из tmux capture-pane
- Показывать прогресс в Telegram

### Tool results formatting
Красивое форматирование результатов тулов:
- Syntax highlighting для кода
- Collapsible для длинных выводов
- Превью для файлов

### Hidden tools filtering
Не показывать тулы которых нет в CLI интерфейсе:
- TodoWrite
- Другие internal тулы
- Нужно исследовать какие именно скрыты

### /shift_tab command
Команда для переключения режима approval:
- Отправляет Shift+Tab в tmux
- Репортит изменение режима: "Allow once → Allow for session"
- Парсит текущий выбор из tmux capture-pane

### Markdown rendering fix
Разобраться почему Markdown не рендерится в Telegram:
- Иногда сообщения приходят plain text вместо formatted
- Проверить escape символов
- Возможно проблема с parse_mode

### Self-hosting: default chat = bot project
Дефолтный личный чат с ботом связан с папкой telegram-bridge:
- Позволяет управлять ботом через самого себя
- Не нужно создавать отдельную группу для разработки бота

## PoC / Research

### telegram-bridge-tmux-only
Эксперимент: использовать только tmux capture-pane без jsonl.
- См. `docs/designs/telegram-bridge-tmux-only.md`
- Плюсы: проще, не зависит от внутреннего формата Claude
- Минусы: парсинг ANSI, нестабильно
