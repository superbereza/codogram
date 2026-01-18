# Start Flow v2 — Onboarding Redesign

**Date:** 2026-01-18
**Status:** Draft

## Overview

Полный редизайн /start flow для широкой аудитории. Вместо требования знать команды — интуитивный onboarding с момента добавления бота в чат.

## Проблемы текущего flow

1. Требует знания `/start` команды
2. Непонятный порядок шагов (create dir → git setup → clone не работает)
3. Нет проверки admin прав до начала
4. Нет переименования чата под проект
5. Ограниченные команды доступны во время setup

## Ограничения

**Поддерживаемые типы чатов:**
- ✅ Supergroups (с topics или без)
- ✅ Regular groups (без topics)
- ❌ Private chats — блокируем с сообщением "Add bot to a group chat"
- ❌ Channels — не поддерживаем

**Один setup на чат:**
Setup flow — синглтон на чат. Если setup уже активен, повторные попытки игнорируются.

## Триггеры onboarding

Flow запускается при:
1. **Бот добавлен в чат** — `my_chat_member` update (aiogram)
2. **`/start` в чате без проекта**
3. **Любое сообщение в чате без проекта**

**Реализация триггера "бот добавлен":**
```python
from aiogram import Router, F
from aiogram.types import ChatMemberUpdated

router = Router()

@router.my_chat_member(
    F.new_chat_member.status.in_({"member", "administrator"})
)
async def on_bot_added(event: ChatMemberUpdated):
    """Trigger when bot is added to chat or granted admin."""
    chat_id = event.chat.id
    # Start onboarding flow...
```

**Важно:** `my_chat_member` (не `chat_member`) — события о БОТЕ, не о других участниках.

## Flow Overview

```
Bot added / message received
         ↓
    base_dir exists?
    ↓ No                      ↓ Yes
    ↓                         ↓
"Configure base_dir first"    Has admin rights?
[Instructions for             ↓ No              ↓ Yes
 ~/.codogram/config.json]     ↓                 ↓
         ↓                 "Grant admin rights   → ASK_SETUP_TYPE
    (blocked)               to continue"
                            [Check rights]
                                ↓
                           [Wait for ChatMemberUpdated
                            OR button press]
                                ↓
                            → ASK_SETUP_TYPE
                                 ↓
                        ┌────────────────────────────────┐
                        │ [Clone repository]             │
                        │ [Connect to existing folder]   │
                        │ [Start new project]            │
                        └────────────────────────────────┘
                                 ↓
                            (see detailed flows below)
                                 ↓
                              LAUNCH
                                 ↓
                            SUCCESS + announcement
```

## Base Directory Check

**Первый шаг — проверка base_dir:**

`base_dir` задаётся в `.env` файле (текущее поведение кода):
```bash
BASE_DIR=/home/user/dev
```

Если `BASE_DIR` не задан или директория не существует:
```
[!] Configure base directory first

Set BASE_DIR in .env file:
BASE_DIR=/home/user/dev

Then restart the bot.
```

**Поведение:** Flow заблокирован до настройки. После настройки `.env` — перезапуск бота.

**Проверка:**
```python
def check_base_dir() -> Path | None:
    """Return base_dir path or None if not configured/exists."""
    base_dir = settings.base_dir
    if not base_dir:
        return None
    path = Path(base_dir).expanduser()
    if not path.exists():
        return None
    return path
```

## Admin Rights

**Требуемые права:**
- `can_change_info` — переименование чата
- `can_manage_topics` — управление topics (опционально)

**Сообщение при отсутствии прав:**
```
[!] Grant admin rights to continue

Bot needs admin rights to:
• Rename chat to match project
• Manage topics for branches

Open chat settings → Administrators → Add bot as admin

[Check rights]
```

**Поведение:**
- Блокируем flow до получения прав
- При `ChatMemberUpdated` с правами — автоматически продолжаем
- Кнопка `[Check rights]` — ручная проверка (если event потерялся)

**При нажатии "Check rights":**
- Права есть → продолжаем к ASK_SETUP_TYPE
- Прав нет → показываем то же сообщение снова

## Concurrency Protection

**Per-chat setup lock:**

Один активный setup flow на чат. Реализация через FSM state:
```python
async def is_setup_in_progress(state: FSMContext) -> bool:
    """Check if setup is already in progress."""
    current = await state.get_state()
    return current and current.startswith("SetupFlow:")
```

**При попытке параллельного setup:**
- Игнорируем (не отвечаем)
- Или показываем: "Setup already in progress"

**Debounce для кнопок:**
Callback handlers должны проверять `callback_query.message.date` — если сообщение старше 5 минут, игнорируем (stale button).

## Меню команд

**Три уровня меню:**

### 1. SETUP_COMMANDS (во время onboarding)
```python
SETUP_COMMANDS = [
    BotCommand(command="start", description="Restart setup"),
    BotCommand(command="reset_all", description="Cancel setup"),
    BotCommand(command="help", description="Get help"),
    BotCommand(command="get_debug_ids", description="Show debug IDs"),
]
```

**Когда регистрировать:** Сразу при входе в setup flow (первое сообщение).

### 2. BASIC_COMMANDS (после setup, non-forum)
```python
# Существующий список без /branch, /finish
```

### 3. FORUM_COMMANDS (после setup, forum)
```python
# Полный список включая /branch, /finish
```

**Когда переключать:** В LAUNCH phase после успешного запуска Claude.

**При вызове недоступной команды во время setup:**
```
[!] Complete project setup first

Available commands:
• /reset_all — cancel setup
• /help — get help
```

**Реализация блокировки:**
Middleware проверяет FSM state. Если `SetupFlow:*` — блокирует все команды кроме `/start`, `/reset_all`, `/help`, `/get_debug_ids`.

## Flow 1: Clone repository

```
User: [Clone repository]
         ↓
Bot: Send repository URL:
     • SSH: `git@github.com:user/repo.git`
     • HTTPS: `https://github.com/user/repo.git`

     [<< Go back]
         ↓
User: https://github.com/user/awesome-project.git
         ↓
Bot: [Cloning...] (progress animation)
         ↓
     git clone into ~/dev/awesome-project
         ↓
     Success?
     ↓ No                              ↓ Yes
     ↓                                 ↓
"Clone failed: {error}"          Chat name ≠ project?
[Retry] [Change URL] [<< Back]        ↓ Yes              ↓ No
                                      ↓                  ↓
                              "Rename chat to            → LAUNCH
                               `awesome-project`?"
                              [Yes] [No]
                                      ↓
                                  → LAUNCH
```

**Rename failed:**
Если переименование чата не удалось:
```
[!] Couldn't rename chat (missing permissions?)
Continuing with project setup...
```
Показываем warning и продолжаем — это не критичная ошибка.

**Обработка ошибок rename:**
```python
async def rename_chat_safe(bot: Bot, chat_id: int, title: str) -> bool:
    """Try to rename chat, return False on failure."""
    try:
        await bot.set_chat_title(chat_id, title)
        return True
    except TelegramBadRequest as e:
        # Not enough rights, chat title too long, etc.
        logger.warning(f"Rename failed: {e}")
        return False
    except TelegramAPIError as e:
        # Network, rate limit, etc.
        logger.warning(f"Rename failed: {e}")
        return False
```

**Валидация URL (уже реализована):**
- Wiki URLs → ошибка
- Blob/tree URLs → ошибка
- Gist → ошибка
- Неверный формат → ошибка

**Извлечение имени из URL:**
```python
# https://github.com/user/awesome-project.git → awesome-project
# git@github.com:user/awesome-project.git → awesome-project
```

### Clone Flow Corner Cases

| Case | Handling |
|------|----------|
| Large repo (>1GB) | Увеличить timeout до 10 мин, показывать progress |
| SSH key not configured | Detect "Permission denied", suggest HTTPS |
| Repo requires auth (private) | Detect 401/403, explain authentication |
| Network interruption | Cleanup partial directory (уже реализовано) |
| Folder with same name exists | Check before clone, offer: [Use existing] [Different name] |
| URL without .git suffix | Valid, works |
| Submodules | Standard clone, no recursive by default |

## Flow 2: Connect to existing folder

```
User: [Connect to existing folder]
         ↓
Bot: ┌─────────────────────────────────────────┐
     │ Select folder to connect:               │
     │                                         │
     │ [my-project]                            │
     │ [another-project]                       │
     │ [scripts]                               │
     │ ...                                     │
     │                                         │
     │        [<]  1/3  [>]                    │
     │                                         │
     │ [View connected projects]               │
     │ [<< Go back]                            │
     └─────────────────────────────────────────┘
         ↓
User: [my-project]
         ↓
     Chat name ≠ "my-project"?
     ↓ Yes              ↓ No
     ↓                  ↓
"Rename chat to        → Check git
 `my-project`?"
[Yes] [No]
     ↓
     → Check git
         ↓
     Has .git?
     ↓ Yes      ↓ No
     ↓          ↓
→ LAUNCH    "Initialize git?"
            [git init] [git init + gh] [No git]
                 ↓
             → LAUNCH
```

**Экран "View connected projects":**
```
User: [View connected projects]
         ↓
Bot: ┌─────────────────────────────────────────┐
     │ Connected projects:                     │
     │                                         │
     │ • codogram → Codogram Dev               │
     │ • personal-agent → PA Bot               │
     │ • scripts → Scripts Chat                │
     │                                         │
     │ Tap chat name to open.                  │
     │                                         │
     │ [<< Back to folders]                    │
     └─────────────────────────────────────────┘
```
Названия чатов — кликабельные ссылки `t.me/c/{id}`.

**Источник списка папок:**
- `base_dir` из `.env` (проверяется на старте flow)
- Все папки первого уровня (не hidden, не symlinks)
- Минус те что уже подключены к Codogram

**Пагинация:**
- По 10 папок на страницу
- Навигация: `[<] 1/3 [>]`
- `[<< Go back]` — возврат к ASK_SETUP_TYPE

**Pagination state в callback_data (не FSM):**
```python
# Callback data format:
# folder_page:0  — первая страница
# folder_page:1  — вторая страница
# folder_select:my-project  — выбор папки
# folder_view_connected  — показать connected
# folder_back  — назад к ASK_SETUP_TYPE
```
Это позволяет не терять pagination при закрытии/открытии Telegram.

**Ссылки на чаты:**
```python
def get_chat_link(chat_id: int, chat_type: str) -> str | None:
    """Generate t.me link or None if not possible."""
    if chat_type == "supergroup":
        # Supergroups have t.me/c/{id} links
        link_id = str(abs(chat_id))[3:]  # remove -100 prefix
        return f"https://t.me/c/{link_id}"
    # Regular groups don't have stable links
    return None
```

**Если ссылка недоступна (regular group):**
```
• codogram → Codogram Dev (no link)
```
Текст без ссылки, пометка "(no link)".

**Folder list — всегда свежий:**
```python
# При каждом входе/возврате в folder select — свежий список
folders = list_available_folders(settings.base_dir)
kb = folder_select_keyboard(folders, page=0)
```
Не кэшируем в FSM state. Пользователь мог создать папку в терминале между шагами.

### Connect Flow Corner Cases

| Case | Handling |
|------|----------|
| Empty base_dir (no folders) | "No folders found in {base_dir}" |
| Hidden folders (.dotfiles) | Skip, don't show |
| Symlinks | Skip, don't follow |
| Very long folder name | Truncate to 30 chars + "..." |
| 100+ folders | Pagination handles it |
| Folder deleted between list and select | Check existence, show error |
| All folders already connected | "All folders connected. Create new project?" |
| New folder created mid-setup | Fresh list on every view |

## Flow 3: Start new project

```
User: [Start new project]
         ↓
Bot: ┌─────────────────────────────────────────┐
     │ Project folder name?                    │
     │                                         │
     │ Suggested: `nikita-and-codogram-bot-dev`│
     │                                         │
     │ [nikita-and-codogram-bot-dev]           │
     │                                         │
     │ Or send custom name                     │
     │                                         │
     │ [<< Go back]                            │
     └─────────────────────────────────────────┘
         ↓
User: [suggested] или "my-custom-name"
         ↓
     Custom name?
     ↓ Yes                    ↓ No
     ↓                        ↓
"Rename chat to              Skip rename
 `my-custom-name`?"               ↓
[Yes] [No]                        ↓
     ↓                            ↓
     └────────────────────────────┘
                   ↓
Bot: ┌─────────────────────────────────────────┐
     │ Git setup for `{folder}`?               │
     │                                         │
     │ [git init]                              │
     │ [git init + gh repo create]             │
     │ [git clone]                             │
     │ [No git]                                │
     │                                         │
     │ [<< Go back]                            │
     └─────────────────────────────────────────┘
```

**Если выбрал git clone после создания папки:**
```
         ↓
     Папка пустая?
     ↓ Yes          ↓ No
     ↓              ↓
ASK_CLONE_URL   "Folder not empty, can't clone"
     ↓          [Clear folder] [<< Go back]
git clone .
     ↓
  → LAUNCH
```

**Примечание:** `git clone` в существующую папку использует `git clone <url> .` (с точкой).

### New Project Flow Corner Cases

| Case | Handling |
|------|----------|
| Chat title is emoji-only | sanitize returns None → ask for manual input |
| Chat title very long (>50 chars) | Truncate, show suggested |
| Folder name collision | Check, warn: "Folder exists. [Use it] [Different name]" |
| `gh` not installed | Detect, show: "Install gh CLI first" |
| `gh` not authenticated | Detect, show: "Run `gh auth login` first" |
| mkdir fails (permissions) | Show error, offer different path |
| Invalid folder name chars | sanitize handles this |

## LAUNCH Phase (атомарная)

```
LAUNCH
  ↓
Phase 1: Filesystem
  ├─ mkdir (if new project)
  ├─ git init / git clone (if selected)
  ↓
  Error? → "{operation} failed: {error}"
           [Retry] [<< Go back]
  ↓
Phase 2: Runtime
  ├─ Create tmux session
  ├─ Launch Claude
  ├─ Save to config
  ├─ Register full menu
  ↓
  Error? → "Failed to start Claude: {error}"
           [Retry] [/reset_all to start over]
  ↓
SUCCESS
```

**Rollback при ошибке:**
- Phase 1 failed → удаляем созданную папку (если создавали)
- Phase 2 failed → убиваем tmux (если создали), НЕ удаляем папку

**Success announcement:**
```
[✓] Project `my-project` ready

Commands available:
• /esc — cancel operation
• /clear — clear context
• /auto_accept — toggle auto-accept
• /thread — new topic
...

Terminal: `tmux attach -t claude-my-project-main`
```

### General Corner Cases

| Case | Handling |
|------|----------|
| /start during active setup | Restart: clear state, start fresh |
| /start from topic during setup | Redirect to General topic or block |
| Bot demoted during setup | Re-check before rename, warn if needed |
| Bot kicked during setup | Clean up state (on next access) |
| Message edited by user | Ignore edits, only process new messages |
| Button clicked multiple times | Debounce via message.date check |
| Private chat | Block: "Add bot to a group chat" |
| Channel | Block: "Channels not supported" |

## Non-forum чаты

Бот работает без topics, но /thread и /branch недоступны.

**При вызове /thread в non-forum чате:**
```
[!] Topics required for /thread

Topics let you run separate Claude sessions
for different tasks in one chat.

To enable:
1. Tap chat name at the top
2. Tap ⋮ (menu) → Edit
3. Enable "Topics"

Then run /thread again.

[Why do I need this?]
```

**"Why do I need this?" раскрывает:**
```
Topics allow:
• Separate Claude sessions per task
• /branch for isolated feature branches
• /finish to merge and archive
• Clean context for each conversation

Without topics, you get one Claude session
for the entire chat.
```

## Навигация Go back

Каждый `[<< Go back]` возвращает на предыдущий шаг:

```
ASK_SETUP_TYPE
    ↓ ↑ Go back
ASK_PROJECT_NAME / ASK_CLONE_URL / ASK_FOLDER_SELECT
    ↓ ↑ Go back                        ↓ ↑ Back to folders
ASK_GIT_CHOICE / ASK_RENAME_CONFIRM   VIEWING_CONNECTED_PROJECTS
    ↓ ↑ Go back
LAUNCH
```

Нет прыжков через несколько шагов — всегда один шаг назад.
`[<< Back to folders]` из VIEWING_CONNECTED_PROJECTS возвращает к ASK_FOLDER_SELECT.

## FSM States

```python
class SetupFlow(StatesGroup):
    awaiting_admin_rights = State()
    awaiting_setup_type = State()       # Clone/Connect/New
    awaiting_clone_url = State()
    awaiting_folder_select = State()    # + pagination page in data
    viewing_connected_projects = State() # View connected screen
    awaiting_project_name = State()
    awaiting_git_choice = State()
    awaiting_rename_confirm = State()
```

## Модульная структура файлов

Чтобы избежать гигантских файлов, разбиваем на модули:

```
src/codogram/
├── domain/
│   ├── states.py                    # Добавить SetupFlow states
│   └── setup_models.py (new)        # SetupContext dataclass
│
├── handlers/
│   └── setup/                        # Новая директория
│       ├── __init__.py              # Export setup_router
│       ├── triggers.py              # my_chat_member, /start, any message
│       ├── admin_check.py           # Admin rights flow, "Check rights"
│       ├── setup_type.py            # Clone/Connect/New selection
│       ├── clone_flow.py            # Clone repository handlers
│       ├── connect_flow.py          # Connect to folder handlers
│       ├── new_project_flow.py      # New project handlers
│       └── launch.py                # Common launch phase
│
├── services/
│   └── setup/                        # Новая директория
│       ├── __init__.py
│       ├── admin_rights.py          # check_bot_admin_rights()
│       ├── folder_list.py           # list_available_folders()
│       ├── chat_rename.py           # rename_chat_safe()
│       ├── git_operations.py        # clone, init, gh create
│       └── project_setup.py         # Atomic setup with rollback
│
├── keyboards/
│   └── setup/                        # Новая директория
│       ├── __init__.py
│       ├── setup_type.py            # Clone/Connect/New buttons
│       ├── folder_select.py         # Folder pagination
│       ├── git_choice.py            # Git setup options
│       └── confirm.py               # Rename confirm, etc.
│
├── middleware/
│   └── setup_blocker.py (new)       # Block commands during setup
│
└── strings.py                       # Добавить setup strings
```

### Ответственности файлов

| Файл | Ответственность |
|------|-----------------|
| `handlers/setup/triggers.py` | Entry points: my_chat_member, /start, any message |
| `handlers/setup/admin_check.py` | Admin rights flow, "Check rights" button |
| `handlers/setup/setup_type.py` | ASK_SETUP_TYPE state, 3 main buttons |
| `handlers/setup/clone_flow.py` | URL input, validation, clone progress |
| `handlers/setup/connect_flow.py` | Folder list, pagination, view connected |
| `handlers/setup/new_project_flow.py` | Name input, git choice |
| `handlers/setup/launch.py` | Common launch logic, announcement |
| `services/setup/admin_rights.py` | `check_bot_admin_rights(chat_id)` |
| `services/setup/folder_list.py` | `list_available_folders(base_dir)` |
| `services/setup/chat_rename.py` | `rename_chat_safe(bot, chat_id, name)` |
| `services/setup/git_operations.py` | git clone/init + `extract_project_name_from_url()` |
| `services/setup/project_setup.py` | Atomic setup with rollback |
| `keyboards/setup/folder_select.py` | `folder_select_kb(folders, page, total)` |
| `middleware/setup_blocker.py` | Block non-setup commands when SetupFlow active |

### Router Registration

```python
# handlers/setup/__init__.py
from aiogram import Router

from .triggers import router as triggers_router
from .admin_check import router as admin_router
from .setup_type import router as type_router
from .clone_flow import router as clone_router
from .connect_flow import router as connect_router
from .new_project_flow import router as new_router
from .launch import router as launch_router

setup_router = Router(name="setup")
setup_router.include_router(triggers_router)
setup_router.include_router(admin_router)
setup_router.include_router(type_router)
setup_router.include_router(clone_router)
setup_router.include_router(connect_router)
setup_router.include_router(new_router)
setup_router.include_router(launch_router)
```

### Миграция с текущей структуры

1. Существующий `handlers/start.py` → deprecate, redirect to `handlers/setup/`
2. Существующий `services/start_flow.py` → частично переиспользовать в `services/setup/`
3. FSM states: добавить `SetupFlow` параллельно с `StartFlow`, постепенно мигрировать

## Утилиты

```python
def get_project_name_from_url(url: str) -> str:
    """Extract project name from git URL."""
    # https://github.com/user/awesome-project.git → awesome-project
    # git@github.com:user/awesome-project.git → awesome-project

def list_available_folders(base_dir: Path) -> list[str]:
    """List folders in base_dir minus those already in codogram config."""

def sanitize_project_name(title: str) -> str | None:
    """Sanitize chat title to valid project name. Already implemented with unidecode."""

def get_chat_link(chat_id: int) -> str:
    """Generate t.me/c/ link from chat_id."""
    # chat_id = -1001234567890 → t.me/c/1234567890
    link_id = str(abs(chat_id))[3:]  # remove -100 prefix
    return f"https://t.me/c/{link_id}"
```

## Implementation Notes

### Bot Restart Recovery

При рестарте бота FSM state сохраняется в Redis (если настроен) или теряется.

**Стратегия:**
- Не persist setup state to config (слишком сложно)
- При потере state — пользователь просто запускает /start заново
- Это acceptable UX для редкого случая

### Admin Rights Re-check

Бот может быть demoted во время setup. Проверяем права перед критическими операциями:
- Перед rename chat
- Не проверяем на каждом шаге (overhead)

### Testing Strategy

| Level | What | How |
|-------|------|-----|
| Unit | Services (folder_list, git_ops) | pytest, mocks |
| Integration | Handler flows | pytest-aiogram |
| E2E | Full flow via Telegram | Telegram MCP |

**E2E test scenarios:**
1. Bot added → full clone flow → success
2. Bot added → connect existing → success
3. Bot added → new project → success
4. Admin rights denied → grant → continue
5. Clone fails → retry → success
6. /reset_all mid-flow → clean state

## Чеклист реализации

### Phase 1: Infrastructure
- [ ] Создать `handlers/setup/` директорию
- [ ] Создать `services/setup/` директорию
- [ ] Создать `keyboards/setup/` директорию
- [ ] Добавить `SetupFlow` в `domain/states.py`
- [ ] Добавить `SETUP_COMMANDS` в `services/menu.py`
- [ ] Создать `middleware/setup_blocker.py`

### Phase 2: Triggers & Admin
- [ ] `handlers/setup/triggers.py` — my_chat_member, /start
- [ ] `handlers/setup/admin_check.py` — rights check, "Check rights"
- [ ] `services/setup/admin_rights.py` — check_bot_admin_rights()

### Phase 3: Setup Type & Clone
- [ ] `handlers/setup/setup_type.py` — 3 buttons
- [ ] `keyboards/setup/setup_type.py` — keyboard builder
- [ ] `handlers/setup/clone_flow.py` — URL validation, clone
- [ ] `services/setup/git_operations.py` — clone logic

### Phase 4: Connect & New Project
- [ ] `handlers/setup/connect_flow.py` — folder list, pagination
- [ ] `keyboards/setup/folder_select.py` — pagination keyboard
- [ ] `services/setup/folder_list.py` — list_available_folders()
- [ ] `handlers/setup/new_project_flow.py` — name, git choice
- [ ] `keyboards/setup/git_choice.py` — git options

### Phase 5: Launch & Finish
- [ ] `handlers/setup/launch.py` — atomic launch
- [ ] `services/setup/project_setup.py` — with rollback
- [ ] `services/setup/chat_rename.py` — rename_chat_safe()
- [ ] Переключение меню после success

### Phase 6: Polish
- [ ] Corner case handling (all tables above)
- [ ] Error messages (strings.py)
- [ ] Concurrency protection

### Phase 7: Testing
- [ ] Unit tests для services
- [ ] Integration tests для handlers
- [ ] E2E tests via Telegram MCP
