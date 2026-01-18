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

## Триггеры onboarding

Flow запускается при:
1. **Бот добавлен в чат** — `ChatMemberUpdated` event
2. **`/start` в чате без проекта**
3. **Любое сообщение в чате без проекта**

## Flow Overview

```
Bot added / message received
         ↓
    Has admin rights?
    ↓ No              ↓ Yes
    ↓                 ↓
"Grant admin rights   → ASK_SETUP_TYPE
 to continue"
    ↓
[Wait for ChatMemberUpdated]
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
```

**Поведение:** Блокируем flow до получения прав. При `ChatMemberUpdated` с правами — продолжаем.

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

### 2. BASIC_COMMANDS (после setup, non-forum)
```python
# Существующий список без /branch, /finish
```

### 3. FORUM_COMMANDS (после setup, forum)
```python
# Полный список включая /branch, /finish
```

**При вызове недоступной команды во время setup:**
```
[!] Complete project setup first

Available commands:
• /reset_all — cancel setup
• /help — get help
```

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
Если переименование чата не удалось (нет прав, API ошибка):
```
[!] Couldn't rename chat (missing permissions?)
Continuing with project setup...
```
Показываем warning и продолжаем — это не критичная ошибка.

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

## Flow 2: Connect to existing folder

```
User: [Connect to existing folder]
         ↓
Bot: ┌─────────────────────────────────────────┐
     │ Available folders:                      │
     │ [my-project]                            │
     │ [another-project]                       │
     │ [scripts]                               │
     │ ...                                     │
     │                                         │
     │ Already connected to Codogram:          │
     │ • codogram → [Codogram Dev](t.me/c/...) │
     │ • personal-agent → [PA Bot](t.me/c/...) │
     │                                         │
     │        [<]  1/3  [>]                    │
     │         [<< Go back]                    │
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

**Источник списка папок:**
- `base_dir` из `~/.codogram/config.json`, fallback `~/dev/`
- Все папки первого уровня
- Минус те что уже в конфиге codogram

**Пагинация:**
- По 10 папок на страницу
- Навигация: `[<] 1/3 [>]`
- `[<< Go back]` — возврат к ASK_SETUP_TYPE

**Ссылки на чаты:**
"Already connected" показывает ссылки на чаты через `t.me/c/{id}`:
```python
# chat_id = -1001234567890
# link = t.me/c/1234567890  (без -100 префикса)
link_id = str(abs(chat_id))[3:]
```
Если пользователь участник чата — откроется. Если нет — Telegram покажет ошибку (это ок).

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
    ↓ ↑ Go back
ASK_GIT_CHOICE / ASK_RENAME_CONFIRM
    ↓ ↑ Go back
LAUNCH
```

Нет прыжков через несколько шагов — всегда один шаг назад.

## FSM States

```python
class SetupFlow(StatesGroup):
    awaiting_admin_rights = State()
    awaiting_setup_type = State()      # Clone/Connect/New
    awaiting_clone_url = State()
    awaiting_folder_select = State()   # + pagination page in data
    awaiting_project_name = State()
    awaiting_git_choice = State()
    awaiting_rename_confirm = State()
```

## Файлы для изменения

| Файл | Изменения |
|------|-----------|
| `handlers/start.py` | Полная переработка под новый flow |
| `handlers/migration.py` | Добавить обработку ChatMemberUpdated для прав |
| `services/start_flow.py` | Новая логика flow |
| `services/menu.py` | Добавить SETUP_COMMANDS |
| `keyboards/setup.py` | Новые клавиатуры (folder select, pagination) |
| `domain/states.py` | Добавить SetupFlow |
| `strings.py` | Новые строки для onboarding |

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

## Чеклист реализации

- [ ] ChatMemberUpdated handler для триггера и отслеживания прав
- [ ] SETUP_COMMANDS и переключение меню
- [ ] ASK_SETUP_TYPE с тремя кнопками
- [ ] Clone flow с валидацией URL
- [ ] Connect flow с пагинацией папок
- [ ] New project flow с git setup
- [ ] Переименование чата (если отличается от проекта)
- [ ] Атомарный LAUNCH с rollback
- [ ] Улучшенная инструкция для /thread в non-forum
- [ ] Блокировка других команд во время setup
- [ ] E2E тесты для всех flow
