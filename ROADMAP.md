# Codogram Roadmap

## Done

### Codogram extraction
- Extracted from personal-agent to standalone repo
- Renamed package telegram_bridge → codogram
- Full git history preserved (242 commits)
- GitHub: superbereza/codogram

### Core
- tmux send-keys для input
- jsonl watch для output
- Chunking (4000 символов)
- Статус символы (●◐✓)

### Multi-session architecture
- Один процесс бота на несколько Claude сессий
- history.jsonl polling для обнаружения сессий (не hooks)
- Project → Chat mapping
- Git worktree support (резолвит project name)
- Авто-определение project name из заголовка чата

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

### Session binding
- Привязка сессии по совпадению текста сообщения
- poll_for_session() для поиска новой сессии
- is_claude_ready() проверка готовности Claude TUI
- Doom-guy loading animation при запуске

### Multi-session topics
- Telegram Forum Topics: каждый топик = отдельная Claude сессия
- ThreadInfo dataclass для per-thread state
- `/session_new [name]` — создать новый топик с Claude
- `/session_close` — закрыть топик и убить tmux
- Magic names для автонейминга (arcane, mystic, celestial...)
- Thread-specific watcher и permission poller
- Session binding по user message для каждого thread
- tmux died detection с уведомлением в топик
- /resume блокировка в мультисессионном режиме

### Security improvements
- shell=False во всех subprocess calls (предотвращает shell injection)
- Валидация project name (только alphanumeric, dash, underscore)
- Unified logging через python logging module

## Backlog

### Auto-accept mode
Автоматическое разрешение всех permission prompts:
- `/auto_accept_mode on|off` команда для включения/выключения
- Поле `auto_accept` в ProjectState (per-project setting)
- Когда включено: автоматически отвечает "y" на все permission prompts
- **Обязательно:** вести лог авто-разрешенных запросов
  - Логировать только запросы на действие (не ответы на вопросы)
  - Формат: timestamp, project, tool_name, arguments summary
  - Уровень: INFO в общий лог
- UI: показывать статус в /status
- Безопасность: только для доверенных проектов

### Voice → Whisper
Голосовые сообщения через Whisper transcription:
- Используем существующий код из bz-merch-assistant
- `ai_bot_core/services/whisper.py`

### Session switching UI
Улучшения для multi-session:
- Inline кнопки для переключения между топиками
- `/sessions` — список активных сессий
- Быстрое переключение без перехода в топик

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

### /settings command
Отображение текущего состояния Claude сессии:
- Текущий режим approval (accept edits, allow all, etc.)
- Количество background tasks
- Парсить из tmux capture-pane статус бар
- Формат: "Mode: Accept edits | Background: 3 tasks"

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

### Reply support
При реплае на сообщение отправлять контекст в tmux:
- Цитировать кусочек сообщения на которое ответили
- Формат: `> цитата\n\nтекст ответа`

### Images and files support
Поддержка отправки картинок и файлов от админа:
- Сохранять в temp/project folder
- Отправлять путь к файлу в tmux
- Возможно: inline images через base64

### Self-hosting: default chat = bot project
Дефолтный личный чат с ботом связан с папкой codogram:
- Позволяет управлять ботом через самого себя
- Не нужно создавать отдельную группу для разработки бота

## PoC / Research

### codogram-tmux-only
Эксперимент: использовать только tmux capture-pane без jsonl.
- См. `docs/designs/2025-12-23-telegram-bridge-tmux-only.md`
- Плюсы: проще, не зависит от внутреннего формата Claude
- Минусы: парсинг ANSI, нестабильно
