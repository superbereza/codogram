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

### Поддержка AskUserQuestion
Полная поддержка AskUserQuestion промптов от Claude:
- Парсинг текста вопроса и вариантов ответа из tmux
- Single-select: тап на кнопку → отправка номера в tmux
- Multi-select: переключение чекбоксов в Telegram, отправка diff при Submit
- Детект опции "Type something" с сообщением "✏️ Type your answer"
- Заголовок с прогрессом: "☐ Title (N/M)" для многовопросных flow
- Автоудаление сообщений при отправке текста или /esc (как permission poller)
- Рефакторинг с dataclasses и helper functions
- См. [docs/designs/done/2026-01-21-askuserquestion-support.md](designs/done/2026-01-21-askuserquestion-support.md)

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
- Защита в `stop-and-restart.sh` от запуска из worktree
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

### Thread/Branch create UX
Улучшенный ввод имени для `/thread` и `/branch`:
- Без аргумента → показать промпт "Thread/Branch name?" с кнопками
- Кнопка [🔮 Magic name] генерирует случайное имя (arcane, mystic...)
- Пользователь может ввести своё имя текстом
- [<<] Go back отменяет операцию
- С аргументом → валидирует и создаёт напрямую (без изменений)
- Flow state очищается при любой новой команде
- См. [docs/designs/done/2026-01-07-thread-branch-create-ux.md](designs/done/2026-01-07-thread-branch-create-ux.md)

### Отображение и управление состоянием сессии
Показ и управление состоянием Claude сессии:
- **/shift_tab команда** — отправляет Shift+Tab в tmux, переключает approval mode
- **/settings улучшения** — показывает approval mode, background tasks, context usage
- **Парсинг статус бара** — парсинг строки под input box (только в idle)
- **Отмена permission при отправке** — отменяет активный permission prompt перед отправкой сообщения
- См. [docs/designs/done/2026-01-07-session-state-display.md](designs/done/2026-01-07-session-state-display.md)

### Унификация статусных сообщений
Все user-facing сообщения централизованы в `strings.py`:
- 170 констант для всех статусов, промптов, ошибок, текстов кнопок
- `STATUS_*` префиксы (`[v]`, `[x]`, `[!]`, `[~]`, `[?]`, `[i]`)
- Паттерн send vs edit: первый edit убирает кнопки, последующие статусы через send
- Единый tone-of-voice во всех handlers
- См. [docs/designs/done/2026-01-17-status-messages-unification.md](designs/done/2026-01-17-status-messages-unification.md)

### Восстановление stale worktree
Обработка удалённых worktrees вместо краша:
- `/resume`, `/start` — детект stale worktree_path, предложить: пересоздать / resume in main / отмена
- `/finish` — warning + архивировать без git cleanup
- `/branch` — fallback на main как base branch
- "Resume in main" архивирует топик (работа над фичей завершена)
- См. [docs/designs/done/2026-01-12-stale-worktree-recovery.md](designs/done/2026-01-12-stale-worktree-recovery.md)

### Фикс gh repo create без коммитов
`gh repo create --push` падал на пустом репо с ошибкой "no commits found".
- Добавлен `git commit --allow-empty -m "Initial commit"` перед `gh repo create --push`

### Отправка картинок и файлов
Отправка картинок и файлов из Telegram в Claude:
- Фото сохраняются в `tmp/input-files/{thread}/` с таймстемпом в имени
- Документы (PDF, txt, md и др.) с whitelist расширений
- Формат: `See file: ./path/to/file` для чтения Claude
- Видео отклоняются (аудио/голосовые обрабатываются через Whisper)
- Защита от path traversal и лимит 20MB
- См. [docs/designs/done/2026-01-17-image-file-input.md](designs/done/2026-01-17-image-file-input.md)

### Verbose mode и улучшения /settings
Per-thread/per-project toggle verbose output и UX настроек:
- `/verbose` — toggle verbose output on/off (индикаторы ● on / ○ off)
- `/settings` inline кнопки для быстрых переключений (/auto_accept, /verbose, /shift_tab, close)
- Короткие hash ID в callback data (фикс для длинных имён tmux сессий)
- Отображение mode с эмодзи: ⏵⏵ accept edits, ⏸ plan mode, default
- Подсказка "(use /shift_tab to cycle)" в настройках
- Кнопка close удаляет сообщение с настройками
- См. [docs/plans/done/2026-01-17-verbose-toggle-plan.md](plans/done/2026-01-17-verbose-toggle-plan.md)

### DM онбординг
Интерактивный онбординг в директ чате с ботом:
- Welcome карусель с обзором возможностей бота
- Валидация окружения (BASE_DIR, tmux, claude, git, gh, whisper)
- Critical проверки блокируют прогресс, optional показывают warnings
- `/check_env` команда для повторной валидации
- `/dashboard` показывает все проекты с количеством активных сессий
- `/intro` для повтора онбординга
- Push-уведомление когда бот добавлен в группу
- Отдельное меню команд для DM
- См. [docs/designs/done/2025-01-18-dm-onboarding.md](designs/done/2025-01-18-dm-onboarding.md)

### Групповая авторизация
Разрешаем использование бота в группах, где хотя бы один админ группы есть в ADMIN_IDS:
- Личка: только пользователи из ADMIN_IDS
- Группа с админом из ADMIN_IDS: любой участник может использовать бота
- Группа без админа из ADMIN_IDS: заблокировано
- Event-driven: события добавления/удаления бота, ухода/понижения админа
- Persistence: allowed_groups хранится в config.json
- Re-validation после перезапуска бота
- Обычные группы: пропускаем проверку админских прав (топики не поддерживаются)
- Супергруппы: проверяем админские права для функций топиков/переименования
- См. [docs/plans/done/2026-01-18-group-authorization-design.md](plans/done/2026-01-18-group-authorization-design.md)

### Реструктуризация проекта
Реорганизация кодовой базы в логические модули:
- `telegram/` — queue, adapters, keyboards, launch animation
- `tmux/` — sessions, commands, window creation
- `claude/` — screen parsing, permission prompts, history.jsonl
- `git/` — worktree, branches, utils
- `core/` — project state, background task coordinator
- См. [docs/designs/done/2026-01-21-project-restructure.md](designs/done/2026-01-21-project-restructure.md)

### Объединение команд thread/branch и упрощение меню
Единые команды вместо отдельных thread/branch/finish:
- `/new_chat` — создать новый чат (thread или branch с worktree)
- `/finish_chat` — завершить чат (архивировать топик)
- `/clear_context` — сбросить контекст Claude (новая сессия)
- `/hard_reset` — полный сброс проекта
- Интуитивные названия без технической терминологии
- Контекстное поведение: из main → thread, из branch → nested branch
- Относительные пути в UI (`./project` вместо полного пути)
- См. [docs/designs/done/2026-01-19-command-merge-design.md](designs/done/2026-01-19-command-merge-design.md)

### Avatar emoji pack
Кастомный эмодзи пак из аватарок участников группы:
- `/exp_avatar_pack` — toggle on/off, создать или удалить пак
- Создание пака при миграции группа → супергруппа (async)
- Добавление аватарки при присоединении участника, удаление при уходе
- Генерация плейсхолдера (буква + цвет) для юзеров без аватарки
- Весёлые рандомные названия: "Cosmic Dolphins", "Epic Titans" и т.д.
- Подсказка с ссылкой на пак при запуске топика (если фича включена)
- Ограничение: Premium нужен для установки кастом эмодзи как иконки топика
- См. [docs/designs/done/2026-01-18-emoji-pack-design.md](designs/done/2026-01-18-emoji-pack-design.md)

### Редизайн set up flow + robust start
Полный редизайн /start flow с устойчивой обработкой ошибок и интуитивным UX настройки:
- Три пути настройки: Clone repository, Connect existing folder, New project
- SetupFlow FSM со состояниями для каждого шага
- SetupBlockerMiddleware блокирует не-setup команды во время flow
- Кнопка Cancel и /reset_all для отмены setup
- Навигация с кнопками Go back
- См. [docs/designs/done/2026-01-18-start-flow-v2.md](designs/done/2026-01-18-start-flow-v2.md)

### Режим ответа на сообщения
Per-chat настройка когда бот должен отвечать:
- **Все сообщения** — отвечать на всё (по умолчанию)
- **Polite** — пропускать сообщения с @упоминаниями других
- **Mentions only** — отвечать только когда бот @упомянут или на него ответили
- Переключение через `/response_mode` или кнопку в `/settings`

### Voice → Whisper транскрипция
Голосовые и аудио файлы транскрибируются через OpenAI Whisper:
- Голосовые (.ogg), аудио файлы (.mp3 и др.), видео-кружочки
- Статус "Transcribing...", затем "«текст» → Claude" при успехе
- Дружелюбные ошибки (файл слишком большой, таймаут, нет речи и т.д.)
- Настройка через OPENAI_API_KEY, OPENAI_BASE_URL, WHISPER_TIMEOUT
- См. [docs/designs/done/2026-01-18-whisper-transcription-design.md](designs/done/2026-01-18-whisper-transcription-design.md)

### Детальное меню verbose mode
Гранулярный контроль над выводом бота через `/verbose` подменю:
- `[full]` — показывать всё (tool calls, auto-accept уведомления)
- `[-5 strings] [+5 strings]` — лимит строк вывода
- `[just headers]` — только названия тулов без содержимого
- `[only current header]` — одно сообщение, обновляется с новым тулом
- `[total silence]` — полная тишина, только финальные ответы

### Toggle bullet point (•)
Отдельная настройка вкл/выкл жирной точки `•` в начале сообщений бота.

### Скрыть/показать thinking
Per-chat toggle для видимости блоков `<thinking>`:
- По умолчанию скрыто для чистоты вывода
- Включить для дебага или обучения

### Сворачиваемые permission prompts
Permission prompts по умолчанию показывают только заголовок:
- Тип действия (Bash, Read, Edit и т.д.)
- Кнопка `[Show more]` раскрывает полный контекст
- Сообщение редактируется на месте

## Beta Test

### Compacting detection
Уведомление когда Claude компактит conversation:
- Парсинг thinking status на ключевое слово "Compacting"
- Одноразовое уведомление `[i] Claude is compacting conversation...`
- Включено для всех, ещё в отладке

### Activity indicators
Отображение что Claude думает/работает:
- Индикатор генерации над input box в tmux
- Парсинг из tmux capture-pane
- Показ thinking status в Telegram
- Toggle: `/exp_thinking_status`

### Input suggestions
Показ саджестов Claude в Telegram:
- Парсинг саджеста из input box (текст с маркером `↵ send`)
- Отображение как ReplyKeyboard для отправки в один тап
- Toggle: `/exp_suggestions`

### Stuck message recovery
Автоопределение и переотправка застрявших сообщений:
- Детект `[Pasted X lines]` или last_sent_message застрявшего в input
- Debounce: отправка Enter только после двух одинаковых состояний
- Предотвращает потерю сообщений из-за race conditions
- См. [docs/designs/done/2026-01-17-stuck-message-recovery.md](designs/done/2026-01-17-stuck-message-recovery.md)

## In Progress

### Auto-suspend & auto-resume
Экономия RAM за счёт убийства idle сессий, auto-resume при сообщении:
- **Auto-suspend:** Убить tmux после 12ч неактивности (тихо, без уведомления)
- **Auto-resume:** Перезапуск Claude когда юзер пишет в мёртвую сессию:
  - Suspended сессия → "Session was suspended. Resuming..."
  - Tmux отсутствует → "Tmux not found. Launching..."
  - Claude упал → "Claude not responding. Relaunching..."
- Трекинг активности через `last_activity_at` + jsonl mtime
- Держим сообщение юзера во время resume, отправляем после готовности Claude
- См. [docs/plans/2026-01-24-auto-suspend-design.md](plans/2026-01-24-auto-suspend-design.md)

### Architecture review and clean up
Ревью архитектуры и уменьшение технического долга.
- Phase 1: реструктуризация проекта ✅
- Phase 2: рефакторинг permission poller ✅
- См. [docs/plans/2026-01-22-architecture-refactoring-roadmap.md](plans/2026-01-22-architecture-refactoring-roadmap.md) — полный бэклог

### Глобальные настройки в личке
Команда `/settings` в личке с ботом для дефолтов всех проектов:
- Verbose mode, response mode, auto-accept и другие настройки
- Новые чаты/треды наследуют эти дефолты
- Per-chat настройки переопределяют глобальные
- Настроил один раз — работает везде

## Backlog

### Безопасное key-value хранилище
Зашифрованное хранилище для чувствительных данных (API ключи, токены, секреты):
- Claude может сохранять и получать секреты без показа в чате
- Шифрование at rest
- Per-project или глобальный scope
- Команды или MCP tool для доступа

### Отправка файлов от Claude
Возможность Claude отправлять файлы в Telegram:
- Отправка сгенерированных файлов (код, картинки, документы) прямо в чат
- MCP tool или специальный формат вывода
- Полезно для экспортов, отчётов, сгенерированных ассетов

### Команда fork
Команда `/fork` для создания копии текущей ветки:
- Форк текущего worktree в новую ветку
- Полезно когда разговор пошёл не туда
- Сохраняет контекст, но начинает новое направление

### Интеграция служебного / личного аккаунта
Подключить Telegram аккаунт к боту:
- **Служебный аккаунт** — читать историю чатов, добавляться в группы, обходить ограничения ботов
- **Личный аккаунт** — получать свои сообщения, отвечать с помощью Claude от своего имени
- MTProto клиент (Telethon) рядом с Bot API
- Нужно исследовать: авторизация, хранение сессии, архитектура bot↔userbot

### Режим чата без проекта
Подключение бота к чату без создания проекта:
- Стартовые worktrees в папке codogram
- Быстрый доступ без полной настройки проекта
- Опция "промоутить" в полноценный проект позже
- Полезно для быстрых вопросов или экспериментов

### Передача имён в многопользовательских чатах
Когда несколько людей используют один чат, передавать кто говорит:
- Инжектить имя отправителя перед сообщением: `[Username]: message`
- Помогает Claude понимать контекст разговора
- Toggle настройка per chat

### Team mode: аватарка и имя пользователя для топиков
В режиме team mode персонализация топиков:
- Иконка топика = аватарка пользователя (из emoji pack)
- Название топика включает имя пользователя
- Легко видеть кто над какой веткой работает
- Требует фичу avatar emoji pack

### Контекст чата для режимов ответа
Передача недавних сообщений чата в Claude в режимах polite/mentions:
- Сохранять последние N сообщений из чата
- Инжектить контекст когда бот отвечает на упоминание/реплай
- Помогает Claude понимать ход разговора

### Инструмент исследования контекста чата
MCP tool для Claude чтобы читать историю Telegram чата:
- Запрос недавних сообщений из текущего чата
- Поиск по юзеру, дате, ключевым словам
- Полезно для assistant-style взаимодействия

### Сокращение спама от тулов
Уменьшение шума от internal tool calls в режиме ассистента:
- Скрывать TodoWrite, Read, Glob и т.д. из вывода
- Показывать только user-relevant результаты
- Связано: Hidden tool calls (silent mode)
- Возможно потребуется изменение архитектуры для комфортного assistant UX

### Персистентное состояние setup flow
Сохранять FSM state в config файл чтобы переживать рестарты бота:
- Сохранять state и data при каждом `state.set_state()` / `state.update_data()`
- Восстанавливать FSM state из config при старте бота
- Очищать сохранённое состояние после завершения setup
- Решает проблему "рестарт во время setup = начинай сначала"

### Reply support
При реплае на сообщение отправлять контекст в tmux:
- Цитировать кусочек сообщения на которое ответили
- Формат: `> цитата\n\nтекст ответа`

### Отрисовка таблиц и диаграмм из текста в картинку
Рендерить таблицы и диаграммы из текста в изображения:
- Конвертация ASCII/markdown таблиц в картинки
- Конвертация mermaid/plantuml диаграмм в картинки
- Улучшенная читаемость в Telegram

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

### Детекция ошибок Claude
Обнаружение падения Claude Code с ошибкой (API errors, проблемы сети и т.д.):
- Исследовать как ошибки отображаются в tmux (API error, connection issues)
- Парсить tmux capture-pane на паттерны ошибок
- Отправить текст ошибки юзеру: "⚠️ Claude ошибка: <текст>. Разберись и /start"
- Детектить появление shell prompt после активного Claude

### Контекст безопасности Telegram
Подкидывать гайдлайны безопасности при старте треда/бранча/проекта:
- Объяснить Claude что безопасно делать в Telegram окружении
- Предупредить об опасных операциях (не убивать tmux и т.д.)
- Project-specific ограничения
- Нужно продумать конкретные гайдлайны

### Защищённая среда для не-разработчиков
Позволить продактам использовать Claude без поломки окружения:
- Механизм отката после сессии
- Или sandbox/изолированное выполнение
- Простое восстановление если что-то сломалось
- Нужен R&D по лучшему подходу

### Очередь сообщений до готовности сессии
Кэширование сообщений пользователя пока сессия привязывается:
- После `/start` или `/branch` привязка сессии занимает ~1-2 минуты
- В это окно сообщения уходят в tmux, но ответы не приходят в Telegram
- Решение: кэшировать сообщения пока `awaiting_new_session=True`
- Отправить все накопленные когда сессия привяжется
- Показывать "⏳ Подключение..." пользователю
- См. баг: [2026-01-07-session-not-immediately-active.md](bugs/active/2026-01-07-session-not-immediately-active.md)

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

### Hardware stats
Отображение CPU/RAM:
- График или текстовый индикатор в /settings
- Мониторинг потребления ресурсов Claude процессом


### Tool results formatting
Красивое форматирование результатов тулов:
- Syntax highlighting для кода
- Collapsible для длинных выводов
- Превью для файлов

### Background process command
`/ctrl_b` отправляет Ctrl+B дважды для фонового запуска процессов:
- Последовательность: Ctrl+B → sleep(0.1) → Ctrl+B
- Полезно когда Claude запускает долгие задачи

### Silent push notifications
Тихие пуши на обычные сообщения, громкие на permissions и остановку:
- Обычные сообщения: `disable_notification=True`
- Permissions, generation stopped: громкий пуш
- Возможно потребуются webhooks для быстрой реакции

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

### Подключение к существующей сессии Claude
Подключить Telegram к Claude сессии, запущенной из терминала:
- Юзер запускает `claude` в tmux на ноуте
- Отправляет `/connect` или `/attach` в Telegram
- Бот находит существующие tmux сессии с Claude
- Показывает список для выбора (или авто-подключение если одна)
- Начинает мониторить сессию на prompts/tool calls

### codogram-tmux-only
Эксперимент: использовать только tmux capture-pane без jsonl.
- См. `docs/designs/2025-12-23-telegram-bridge-tmux-only.md`
- Плюсы: проще, не зависит от внутреннего формата Claude
- Минусы: парсинг ANSI, нестабильно

### Ollama launch
Запуск Claude Code CLI с другими моделями через Ollama:
- Запуск codogram с локальными LLM вместо Claude API
- Полезно для тестирования, разработки или экономии
- Исследовать: как Claude Code работает с разными бэкендами моделей
