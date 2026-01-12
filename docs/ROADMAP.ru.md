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
- `/thread_create [name]` — создать новый топик с Claude
- `/thread_delete` — закрыть топик и убить tmux
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

### Telegramify-markdown интеграция
Полная конвертация GFM → MarkdownV2 через библиотеку telegramify-markdown:
- Claude генерирует GFM Markdown (заголовки, **bold**, списки)
- telegramify-markdown конвертирует в Telegram MarkdownV2
- Централизованная конвертация в telegram_queue.py
- Fallback на plain text при ошибках парсинга
- См. [docs/designs/done/2025-01-04-telegramify-markdown-integration.md](designs/done/2025-01-04-telegramify-markdown-integration.md)

### Рефакторинг архитектуры бота
Слоистая архитектура вместо монолитного bot.py (1500+ строк → 0):
- **handlers/** — Telegram хендлеры команд (start, sessions, threads, branches, settings, messages, permissions)
- **services/** — Бизнес-логика (start_flow, branch, message_router, launch)
- **middleware/** — AdminMiddleware для глобальной защиты админов
- **domain/** — Модели, валидаторы, FSM состояния
- **adapters/** — telegram.py (send_with_retry)
- TelegramQueue инжектится через aiogram DI
- StartFlowService с паттерном FlowAction/FlowResult
- 236 тестов, E2E регрессионное тестирование через Telegram MCP
- См. [docs/designs/done/2025-12-27-bot-refactoring/](designs/done/2025-12-27-bot-refactoring/)

### Редизайн меню
Реорганизация команд бота для удобства:
- Единый `/finish` для worktree и обычных топиков
- Короткие алиасы: `/thread`, `/branch`
- Deprecated команды редиректят: `/thread_delete` → "Use /finish"
- Архивация топиков вместо удаления (закрытие + иконка 📁)
- См. [docs/designs/done/2025-01-03-menu-redesign.md](designs/done/2025-01-03-menu-redesign.md)

### Session resume
Восстановление сессии Claude после краша или разархивации топика:
- Хранение session_id в ThreadInfo
- При /start в архивированном топике: `claude --resume <session_id>`
- Сохраняет контекст диалога вместо старта с нуля
- Worktrees сохраняются после /finish для удобного resume
- См. [docs/designs/done/2026-01-05-session-resume.md](designs/done/2026-01-05-session-resume.md)

### E2E тестовая структура
Ручные E2E тесты, выполняемые Claude через Telegram MCP:
- Тестовые наборы: smoke (~2 мин), critical (~15 мин), full (~30 мин)
- Тесты по командам: start, sessions, threads, branches, finish, permissions, watcher
- MCP инструменты для отправки команд, чтения ответов, нажатия кнопок
- Workflow документирования багов с репортами в `docs/bugs/active/`
- См. [docs/designs/done/2026-01-06-e2e-test-structure.md](designs/done/2026-01-06-e2e-test-structure.md)

### Безопасный конфиг для worktrees
Конфиг перенесён в `~/.codogram/` для избежания проблем с worktrees:
- `pip install -e` из worktree больше не ломает main бота
- Новый `dev-run.sh` для тестирования из worktrees (использует PYTHONPATH)
- Защита в `restart.sh` от запуска из worktree
- См. [docs/designs/done/2026-01-07-worktree-safe-config.md](designs/done/2026-01-07-worktree-safe-config.md)

### Миграция группа → супергруппа
Обработка смены chat_id при включении топиков в существующей группе:
- Telegram меняет chat_id при конвертации группы в супергруппу (форум)
- Слушаем событие `message.migrate_to_chat_id`
- Автообновление chat_id в конфиге при миграции
- Scope-based меню: базовое для групп, расширенное (/branch, /finish) для форумов
- Меню регистрируется при старте бота и при /start
- См. [docs/designs/done/2026-01-07-group-to-supergroup-migration.md](designs/done/2026-01-07-group-to-supergroup-migration.md)

### Поддержка MCP trust prompt
Обнаружение и отображение промптов доверия MCP серверам:
- Парсинг box-style UI с символами `╭╮╯╰│`
- Enum `PromptType` для расширяемой классификации типов промптов
- MCP промпты показываются в Telegram с теми же кнопками что обычные
- Auto-accept обходится для MCP промптов (безопасность)
- См. [docs/designs/done/2026-01-07-mcp-trust-prompt.md](designs/done/2026-01-07-mcp-trust-prompt.md)

### Атомарные батчи permission сообщений
Фикс перемешивания permission сообщений с launch_animation:
- Добавлено поле `reply_markup` в `OutgoingBatch` (применяется к последнему сообщению)
- Permission poller отправляет body + options + keyboard одним атомарным enqueue
- Другие сообщения не могут вклиниться между частями permission prompt
- См. [docs/bugs/fixed/2026-01-12-permission-messages-interleaving.md](bugs/fixed/2026-01-12-permission-messages-interleaving.md)

## Backlog

### Thread create UX
Улучшить `/thread_create`:
- Без аргумента → показать кнопки с вариантами имён (magic names)
- Или поле ввода "Введите название"
- Убрать необходимость вводить имя в той же строке

### Отображение и управление состоянием сессии
Показ и управление состоянием Claude сессии:
- **/shift_tab команда** — отправляет Shift+Tab в tmux, репортит изменение ("Allow once → Allow for session")
- **/settings улучшения** — текущий режим approval, количество background tasks
- **Индикатор контекстного окна** — сколько осталось до compact (парсить из jsonl или tmux screen)
- Парсить статус бар из tmux capture-pane
- Формат: "Mode: Accept edits | Background: 3 | Context: 45%"

### Activity indicators
Отображение что Claude думает/работает:
- "thinking..." когда Claude обрабатывает
- Throbber/typing indicator
- Слова типа "Hmm", "Let me think"

### Очередь сообщений до готовности сессии
Кэширование сообщений пользователя пока сессия привязывается:
- После `/start` или `/branch` привязка сессии занимает ~1-2 минуты
- В это окно сообщения уходят в tmux, но ответы не приходят в Telegram
- Решение: кэшировать сообщения пока `awaiting_new_session=True`
- Отправить все накопленные когда сессия привяжется
- Показывать "⏳ Подключение..." пользователю
- См. баг: [2026-01-07-session-not-immediately-active.md](bugs/active/2026-01-07-session-not-immediately-active.md)

### Tool visibility R&D
Исследование и улучшение отображения тулов:
- **Tool progress display** — показ прогресса выполнения (сейчас парсится, но не показывается)
- **Hidden tools filtering** — не показывать TodoWrite и другие internal тулы
- **Инсайт:** В Claude первая строка статична (Task/Tool name), остальные бегут:
  ```
  Task(Implement Task 1: Screen Parser)
    ⎿  Read 46 lines
       Read 30 lines
       Waiting…
  ```
- Из jsonl приходит первая строка — на ней можно якориться
- Нужно исследовать какие тулы скрыты в CLI

### Reply support
При реплае на сообщение отправлять контекст в tmux:
- Цитировать кусочек сообщения на которое ответили
- Формат: `> цитата\n\nтекст ответа`

### Migrate strings to strings.py
Перенести все захардкоженные строки в `src/codogram/strings.py`:
- handlers/*.py — ответы на команды
- launch_animation.py — статусы запуска
- history_watcher.py — уведомления
- keyboards.py — кнопки
- services/start_flow.py — кнопки wizard'а
- См. `docs/specs/tone-of-voice.md` для гайдлайнов

---

### Регистрация ручного топика
Когда `/start` вызывается в созданном вручную топике:
- Если возможен resume (архивный топик с session_id) → resume без вопросов
- Иначе показать меню: "Создать тред" / "Создать worktree"
- Позволяет использовать стандартный UI Telegram для создания топиков

### Улучшение надёжности очереди
Повышение устойчивости TelegramQueue:
- **Retry на network errors** — `ServerDisconnectedError` сейчас не ретраится, сообщение теряется
- **1 rps rate limiting** — проактивный троттлинг чтобы не попадать в лимиты Telegram
- **Exponential backoff** — для retry при rate limit

### Детекция выхода Claude
Обнаружение нормального выхода Claude (не краша):
- Показывать `[~] Claude exited. Use /start to restart.`
- Определять shell prompt после исчезновения Claude UI
- Трекать `claude_was_active` чтобы избежать false positives на старте
- Отличать shell prompt `❯` от Claude selector `❯ 1. Yes`
- См. откаченную попытку: 8b6baf8 (были false positives)

### Cleanup command
Явное удаление архивных веток когда нужно место или git cleanup:
- `/cleanup` — список архивных веток с днями неактивности
- `/cleanup <branch>` — удалить конкретную ветку
- Удаляет worktree и git branch, сохраняет session jsonl
- См. [docs/designs/2026-01-05-cleanup-command.md](designs/2026-01-05-cleanup-command.md)

### GitHub Actions CI
- Workflow для запуска тестов на PR
- pytest + type checking

### Voice → Whisper
Голосовые сообщения через Whisper transcription:
- Используем существующий код из bz-merch-assistant
- `ai_bot_core/services/whisper.py`

### Pin startup message
Пинить сообщение при запуске сессии:
- `Claude started in claude-codogram-sublime`
- `Connect: tmux attach -t claude-codogram-sublime`
- Анпинить предыдущее при рестарте

### Hardware stats
Отображение CPU/RAM:
- График или текстовый индикатор в /settings
- Мониторинг потребления ресурсов Claude процессом

### Compacting indicator
Отображение процесса компактинга контекста:
- Детектить compacting из tmux capture-pane
- Показывать прогресс в Telegram

### Tool results formatting
Красивое форматирование результатов тулов:
- Syntax highlighting для кода
- Collapsible для длинных выводов
- Превью для файлов

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

### Ultrathink mode
`/ultrathink_mode` toggle, добавляет " ultrathink" к каждому сообщению:
- Хранить в per-project settings
- Показывать статус при /start

### Background process command
`/ctrl_b` отправляет Ctrl+B дважды для фонового запуска процессов:
- Последовательность: Ctrl+B → sleep(0.1) → Ctrl+B
- Полезно когда Claude запускает долгие задачи

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
- Заменить на `` `•` `` или другой символ

## PoC / Research

### codogram-tmux-only
Эксперимент: использовать только tmux capture-pane без jsonl.
- См. `docs/designs/2025-12-23-telegram-bridge-tmux-only.md`
- Плюсы: проще, не зависит от внутреннего формата Claude
- Минусы: парсинг ANSI, нестабильно
