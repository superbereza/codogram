# Codogram Roadmap

[English version](ROADMAP.md)

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

### Interactive prompts
- Уточняющие вопросы от Claude с кнопками вариантов ответа (plan mode → AskUserQuestion)

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

### Telegram Rate Limiter
- TelegramQueue класс с FIFO очередью для предотвращения 429 (flood control)
- OutgoingBatch для группировки сообщений
- enqueue() возвращает message IDs для cleanup
- enqueue_nowait() для fire-and-forget
- Retry без parse_mode при Markdown ошибках

### Markdown underscore escaping
- Telegram интерпретирует `_text_` как курсив, ломая snake_case
- Экранирование `_` → `\_` вне code blocks перед отправкой
- На regex, централизованно в telegram_queue.py

### Security improvements
- shell=False во всех subprocess calls (предотвращает shell injection)
- Валидация project name (только alphanumeric, dash, underscore)
- Unified logging через python logging module

### Project initialization wizard
Интерактивный выбор способа инициализации проекта при `/start`:
- **Existing local repo** — подключиться к существующему git репозиторию
- **Clone from GitHub** — `git clone <url>` + подключение
- **New repo** — `git init` + `gh repo create` + подключение
- Inline кнопки для выбора варианта
- Автосоздание tmux сессии в выбранной директории

### Thread session mixup fix
- Баг: при создании новой сессии в одном топике, другие топики теряли привязку
- Решение: Session Binder — `/new`, `/clear` команды + `awaiting_new_session` флаг
- См. [docs/bugs/fixed/2025-12-29-session-binding-race-condition.md](bugs/fixed/2025-12-29-session-binding-race-condition.md)

### Interactive setup script
- `./setup.sh` — интерактивная установка зависимостей
- Определение ОС (Linux/macOS)
- Интерактивный селектор (числа для toggle, работает в Docker)
- Проверка и установка: python3, brew (macOS), tmux, git, gh, claude
- Создание venv, pip install
- Настройка .env (токен бота, admin ID)
- См. [docs/designs/done/2025-12-30-setup-script.md](designs/done/2025-12-30-setup-script.md)

### Git worktree isolation
Изолированные ветки с отдельными директориями:
- `/branch_create [name]` — создать worktree + топик + Claude сессию
- `/branch_finish` — смержить ветку, удалить worktree и топик
- Unified thread-first flow: топик создаётся первым, статусы идут в него
- Magic names с suffix fallback (arcane-2, arcane-3...)
- См. [docs/designs/done/2025-12-30-git-worktree-support.md](designs/done/2025-12-30-git-worktree-support.md)

### Open source release
- LICENSE файл (GPL v3)
- Репозиторий публичный

### Auto-accept mode
Автоматическое подтверждение permission prompts:
- `/auto_accept` — toggle on/off
- `/auto_accept reset all` — сбросить все настройки
- Per-thread/per-project настройки
- Пропускает session-wide permissions ("allow all", "for session")
- Уведомления через TelegramQueue
- `/settings` и `/help` команды

### Queue-level chunking
Централизованное чанкование сообщений в TelegramQueue:
- Сообщения >4000 символов автоматически разбиваются
- Убрано дублирование кода из watcher.py и permission_poller.py
- См. [docs/designs/done/2026-01-03-queue-level-chunking.md](designs/done/2026-01-03-queue-level-chunking.md)

## Backlog

### Bot refactoring
Рефакторинг архитектуры бота — слоёная структура:
- handlers → services → domain → adapters
- Убрать дублирование кода
- Очистить deprecated поля
- См. [docs/designs/2025-12-27-bot-refactoring/](designs/2025-12-27-bot-refactoring/)

### GitHub Actions CI
- Workflow для запуска тестов на PR
- pytest + type checking

### Migrate strings to strings.py
Перенести все захардкоженные строки в `src/codogram/strings.py`:
- bot.py — основной объём (~50 строк)
- launch_animation.py — статусы запуска
- history_watcher.py — уведомления
- keyboards.py — кнопки
- start_flow.py — кнопки wizard'а
- См. `docs/specs/tone-of-voice.md` для гайдлайнов

### Voice → Whisper
Голосовые сообщения через Whisper transcription:
- Используем существующий код из bz-merch-assistant
- `ai_bot_core/services/whisper.py`

### Pin startup message
Пинить сообщение при запуске сессии:
- `🚀 Claude запущен в claude-codogram-sublime`
- `Подключиться: tmux attach -t claude-codogram-sublime`
- Анпинить предыдущее при рестарте

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
- **Hardware stats** — график CPU/RAM использования

### Thread create UX
Улучшить `/thread_create`:
- Без аргумента → показать кнопки с вариантами имён (magic names)
- Или поле ввода "Введите название"
- Убрать необходимость вводить имя в той же строке

### /shift_tab command
Команда для переключения режима approval:
- Отправляет Shift+Tab в tmux
- Репортит изменение режима: "Allow once → Allow for session"
- Парсит текущий выбор из tmux capture-pane

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

### Forward unhandled commands
`/команды` без хэндлера прокидывать в Claude как есть:
- Сейчас добавляются в tmux с двумя слэшами, не отправляются
- Нужен fallback в `on_message` или отдельный хэндлер

### Tool progress display
Показывать прогресс выполнения инструментов:
- Расширить Task 5 в плане permission-detection
- Сейчас `ToolProgress` парсится, но не отображается (pass)
- **Инсайт:** В Claude первая строка статична (Task/Tool name), остальные бегут
  ```
  Task(Implement Task 1: Screen Parser)
    ⎿  Read 46 lines
       Read 30 lines
       Waiting…
  ```
- Из jsonl приходит первая строка — на ней можно якориться

### Ultrathink mode
`/ultrathink_mode` toggle, добавляет " ultrathink" к каждому сообщению:
- Хранить в per-project settings
- Показывать статус при /start

### Context window indicator
Показывать сколько осталось до compact:
- Парсить из jsonl (если есть) или tmux screen
- Показывать в /settings и/или в статусной строке

### Ctrl+B command
`/ctrl_b` отправляет Ctrl+B в tmux:
- Полезно для vim-mode или tmux prefix

### Silent push notifications
Тихие пуши на обычные сообщения, громкие на permissions и остановку:
- Обычные сообщения: `disable_notification=True`
- Permissions, generation stopped: громкий пуш
- Возможно потребуются webhooks для быстрой реакции

### Silent mode
Режим без показа tool calls, только финальные генерации:
- Команда `/silent` для переключения
- Фильтровать TOOL_USE, TOOL_RESULT, показывать только TEXT

### Thread summarization
Суммаризация длинных тредов (под вопросом):
- Команда `/summary` или автоматически при N сообщениях
- Использовать Claude API для суммаризации
- Вопрос: нужно ли это если есть scroll в Telegram?

### Fix bullet point rendering
Заменить большую точку `•` на точку в code block:
- `•` плохо рендерится в некоторых клиентах
- Заменить на `\`•\`` или другой символ

### Markdown to Telegram converter
Библиотека для конвертации обычного MD в TG-совместимый:
- Таблицы, headers не рендерятся в Telegram
- Поискать готовые решения (telegramify-markdown, etc.)

## PoC / Research

### codogram-tmux-only
Эксперимент: использовать только tmux capture-pane без jsonl.
- См. `docs/designs/2025-12-23-telegram-bridge-tmux-only.md`
- Плюсы: проще, не зависит от внутреннего формата Claude
- Минусы: парсинг ANSI, нестабильно
