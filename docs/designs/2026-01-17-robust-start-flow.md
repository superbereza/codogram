# Robust /start Flow

**Date:** 2026-01-17
**Status:** Planned

## Overview

Атомарность и error recovery для flow создания проекта. Решает проблемы:
- Partial state при ошибке clone/init
- Непонятные ошибки (wiki URL)
- Доступность Claude команд до готовности проекта
- Кириллица в названии чата → невалидный project_name

## Проблема

При ошибке на этапе создания проекта (clone fails, init fails):
1. Project частично создаётся в config
2. `/clear`, `/start` ведут себя непредсказуемо
3. Пользователь не понимает как выйти из состояния

Пример: wiki URL `github.com/.../wiki/...` даёт cryptic git error, project остаётся в broken state.

## Решения

### 1. Атомарность /start flow

**Двухфазный подход:**

1. **Фаза подготовки** — все операции с файловой системой (clone, mkdir, git init) выполняются ДО создания записи в config
2. **Фаза регистрации** — только если фаза 1 успешна, создаём project в config и запускаем Claude

**Cleanup при ошибке:**
- Удаляем созданную директорию
- НЕ создаём запись в config
- Показываем понятную ошибку

### 2. Валидация URL

**Невалидные URL для clone:**
- GitHub wiki: `/wiki/` в URL
- GitHub blob/tree: `/blob/` или `/tree/` в URL
- Gist: `gist.github.com`

```python
def validate_git_url(url: str) -> tuple[bool, str | None]:
    """Returns (is_valid, error_message)."""
    if "/wiki/" in url:
        return False, "This is a wiki page, not a repository"
    if "/blob/" in url or "/tree/" in url:
        return False, "This is a file link. Use repository URL without /blob/ or /tree/"
    if "gist.github.com" in url:
        return False, "Gists cannot be cloned as projects"
    return True, None
```

**При невалидном URL — retry без restart:**
- Остаёмся в `waiting_clone_url` FSM state
- Показываем ошибку + "Send valid URL"
- Пользователь шлёт новый URL

### 3. require_project_ready()

Helper по паттерну `require_forum_group()`:

```python
async def require_project_ready(message: Message, telegram_queue: TelegramQueue) -> bool:
    """Check if project is fully ready (cwd + tmux + Claude ready)."""
    project = project_manager.get_by_chat(message.chat.id)
    if not project or not project.cwd:
        await telegram_queue.reply(message, strings.PROJECT_NOT_READY)
        return False

    thread = project.threads.get(message.message_thread_id)
    if not thread:
        await telegram_queue.reply(message, strings.PROJECT_NOT_READY)
        return False

    tmux_name = thread.get_tmux_session(project.project_name)
    if not is_tmux_session_exists(tmux_name):
        await telegram_queue.reply(message, strings.CLAUDE_NOT_RUNNING)
        return False

    tmux = TmuxSession(tmux_name, project.cwd)
    if not tmux.is_claude_ready():
        await telegram_queue.reply(message, strings.CLAUDE_STARTING)
        return False

    return True
```

**Использование:**

```python
@router.message(Command("clear"))
async def cmd_clear(message: Message, telegram_queue: TelegramQueue):
    if not await require_project_ready(message, telegram_queue):
        return
    # ... остальная логика
```

### 4. /reset_all команда

Доступна только на этапе сетапа (до запуска Claude):
- Удаляет project из config
- Удаляет созданную директорию (если была создана)
- Позволяет начать /start заново

После успешного запуска Claude — команда недоступна.

### 5. sanitize_project_name с unidecode

```python
from unidecode import unidecode

def sanitize_project_name(title: str) -> str | None:
    if not title:
        return None

    sanitized = unidecode(title)  # "Мой Проект" → "Moj Proekt"
    sanitized = sanitized.lower()
    sanitized = re.sub(r'[^a-z0-9_-]', '-', sanitized)
    sanitized = re.sub(r'-+', '-', sanitized)
    sanitized = sanitized.strip('-')

    if not sanitized or len(sanitized) > 50:
        return None

    return sanitized
```

**Примеры:**
- "Мой Проект 🚀" → `moj-proekt`
- "Test Project" → `test-project`
- "日本語プロジェクト" → `ri-ben-yu-puroziekuto`

### 6. Анонс команд после успешного запуска

**Формат сообщения:**

```
[v] Project `{project_name}` ready

Commands available in this chat:
• /esc — cancel operation
• /clear — clear context
• /auto_accept — toggle auto-accept
{forum_commands}

To see Claude's UI, run in terminal:
tmux attach -t {tmux_name}
```

**Forum-only команды (добавляются если `chat.is_forum`):**
```
• /thread — new topic
• /branch — new branch + topic
• /finish — merge and archive
```

## Файлы для изменения

| Файл | Изменения |
|------|-----------|
| `domain/validators.py` | `sanitize_project_name` с unidecode |
| `services/start_flow.py` | Атомарность, валидация URL, retry flow |
| `handlers/sessions.py` | `require_project_ready()` в /clear, /new, /esc |
| `handlers/common.py` | `require_project_ready()` helper |
| `handlers/start.py` | /reset_all команда, анонс команд |
| `strings.py` | Новые константы для ошибок и анонса |

## Константы strings.py

```python
# Validation errors
GIT_URL_INVALID_WIKI = f"{STATUS_ERR} This is a wiki page, not a repository"
GIT_URL_INVALID_BLOB = f"{STATUS_ERR} This is a file link. Use repository URL"
GIT_URL_INVALID_GIST = f"{STATUS_ERR} Gists cannot be cloned as projects"

# Project state
PROJECT_NOT_READY = f"{STATUS_WARN} Project not ready. Use /start first"
CLAUDE_NOT_RUNNING = f"{STATUS_WARN} Claude not running. Use /start to launch"
CLAUDE_STARTING = f"{STATUS_WARN} Claude is starting... wait a moment"

# Success announcement
PROJECT_READY = f"{STATUS_OK} Project `{{name}}` ready"
PROJECT_COMMANDS_HEADER = "Commands available in this chat:"
PROJECT_ATTACH_HINT = """
To see Claude's UI, run in terminal:
`tmux attach -t {{tmux_name}}`"""
```

## Чеклист

- [ ] Добавить unidecode в `sanitize_project_name`
- [ ] Добавить `validate_git_url()` с проверкой wiki/blob/gist
- [ ] Retry flow при невалидном URL (остаёмся в FSM state)
- [ ] Атомарность: project entry после успешного clone/init
- [ ] Cleanup при ошибке: удаление директории
- [ ] `require_project_ready()` helper
- [ ] Применить helper в /clear, /new, /esc
- [ ] /reset_all команда (только до запуска Claude)
- [ ] Анонс команд после успешного запуска (по типу чата)
- [ ] Константы в strings.py
- [ ] E2E тесты для error cases
