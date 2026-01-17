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
- Неверный формат: не начинается с `https://`, `git@`, `ssh://`

```python
def validate_git_url(url: str) -> tuple[bool, str | None]:
    """Returns (is_valid, error_string). Uses constants from strings.py."""
    if "/wiki/" in url:
        return False, strings.GIT_URL_INVALID_WIKI
    if "/blob/" in url or "/tree/" in url:
        return False, strings.GIT_URL_INVALID_BLOB
    if "gist.github.com" in url:
        return False, strings.GIT_URL_INVALID_GIST
    if not url.startswith(("https://", "git@", "ssh://")):
        return False, strings.GIT_URL_INVALID_FORMAT
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

**Использование во всех командах требующих готовый проект:**

```python
# sessions.py
@router.message(Command("clear"))
@router.message(Command("new"))
@router.message(Command("esc"))

# threads.py
@router.message(Command("thread"))

# branches.py
@router.message(Command("branch"))

# finish.py
@router.message(Command("finish"))
```

Все эти команды начинаются с:
```python
if not await require_project_ready(message, telegram_queue):
    return
```

### 4. /reset_all команда

Команда для сброса проекта и начала с нуля.

**Flow:**

```
/reset_all
│
├─ Проект не найден
│  └─ `[i]` Nothing to reset. Use /start to begin.
│
├─ Setup phase (session_id = None)
│  └─ Сразу чистим (нечего терять):
│     • Удаляем из config
│     • Удаляем директорию (если пустая/partial)
│     └─ `[v]` Reset complete. Use /start to begin.
│
└─ Рабочий проект (session_id есть)
   │
   ├─ Шаг 1: Подтверждение
   │  `[?]` Reset project `{name}`?
   │
   │  This will disconnect Claude and clear settings.
   │
   │  [Continue] [Cancel]
   │
   └─ Шаг 2: Директория
      │
      ├─ Не существует → чистим config, done
      │
      ├─ Есть uncommitted changes
      │  `[!]` Uncommitted changes in `{path}`
      │  [Keep directory] [Delete anyway] [[<<] Go back]
      │
      └─ Всё чисто
         `[?]` Delete directory `{path}`?
         [Keep] [Delete] [[<<] Go back]
```

**Результат:**
```
`[v]` Project reset

• Config cleared
• Claude stopped
• Directory kept at `{path}` / Directory deleted

/start to begin new project
```

**Helper для определения setup phase:**
```python
def is_setup_phase(project: Project) -> bool:
    """True if Claude never ran in main thread."""
    main_thread = project.threads.get(None)
    if not main_thread or not main_thread.session_id:
        return True
    return False
```

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
| `domain/validators.py` | `sanitize_project_name` с unidecode, `validate_git_url()` |
| `services/start_flow.py` | Атомарность, retry flow, `is_setup_phase()` |
| `handlers/sessions.py` | `require_project_ready()` в /clear, /new, /esc |
| `handlers/threads.py` | `require_project_ready()` в /thread |
| `handlers/branches.py` | `require_project_ready()` в /branch |
| `handlers/finish.py` | `require_project_ready()` в /finish |
| `handlers/common.py` | `require_project_ready()` helper |
| `handlers/start.py` | /reset_all команда (multi-step flow), анонс команд |
| `keyboards/reset.py` | Клавиатуры для /reset_all flow |
| `strings.py` | Новые константы (URL validation, reset, buttons, announcement) |

## Константы strings.py

```python
# --- URL Validation ---
GIT_URL_INVALID_WIKI = f"{STATUS_ERR} This is a wiki page, not a repository"
GIT_URL_INVALID_BLOB = f"{STATUS_ERR} This is a file link. Use repository URL"
GIT_URL_INVALID_GIST = f"{STATUS_ERR} Gists cannot be cloned as projects"
GIT_URL_INVALID_FORMAT = f"{STATUS_ERR} Invalid URL. Use https:// or git@ format"

# --- Project State ---
PROJECT_NOT_READY = f"{STATUS_WARN} Project not ready. Use /start first"
CLAUDE_NOT_RUNNING = f"{STATUS_WARN} Claude not running. Use /start to launch"
CLAUDE_STARTING = f"{STATUS_WARN} Claude is starting... wait a moment"

# --- Reset ---
RESET_NO_PROJECT = f"{STATUS_INFO} Nothing to reset. Use /start to begin."
RESET_COMPLETE = f"{STATUS_OK} Reset complete. Use /start to begin."
RESET_CONFIRM = f"""{STATUS_QUESTION} Reset project `{{name}}`?

This will disconnect Claude and clear settings."""
RESET_UNCOMMITTED = f"{STATUS_WARN} Uncommitted changes in `{{path}}`"
RESET_DIR_CHOICE = f"{STATUS_QUESTION} Delete directory `{{path}}`?"
RESET_DONE = f"""{STATUS_OK} Project reset

• Config cleared
• Claude stopped
• Directory {{dir_status}}

/start to begin new project"""

# --- Buttons ---
BTN_CONTINUE = "Continue"
BTN_KEEP_DIR = "Keep directory"
BTN_DELETE_DIR = "Delete"
BTN_DELETE_ANYWAY = "Delete anyway"
BTN_GO_BACK = "[<<] Go back"

# --- Success Announcement ---
PROJECT_READY = f"{STATUS_OK} Project `{{name}}` ready"
PROJECT_COMMANDS_HEADER = "Commands available in this chat:"
PROJECT_ATTACH_HINT = """
To see Claude's UI, run in terminal:
`tmux attach -t {{tmux_name}}`"""
```

## Чеклист

**Validators & Sanitization:**
- [ ] Добавить unidecode в `sanitize_project_name`
- [ ] Добавить `validate_git_url()` с точными GitHub паттернами (см. Note 4)

**Clone & Cleanup:**
- [ ] `git_clone()` cleanup при ошибке (см. Note 1)
- [ ] Атомарность: project entry после успешного clone/init

**FSM & Retry:**
- [ ] `FlowAction.ASK_CLONE_URL_RETRY` для retry без очистки state (см. Note 2)

**Concurrency:**
- [ ] File locking в `ProjectManager._save()` (см. Note 3)

**Project Ready Checks:**
- [ ] `require_tmux_exists()` для /clear, /esc
- [ ] `require_claude_ready()` для /new, /thread, /branch, /finish
- [ ] (см. Note 8 для mapping)

**Setup Phase & Legacy:**
- [ ] `is_setup_phase()` с fallback на legacy fields (см. Note 5)

**/reset_all Command:**
- [ ] Multi-step flow с go back
- [ ] Project-level scope (не topic-level) (см. Note 6)
- [ ] Uncommitted changes detection (см. Note 7)
- [ ] Worktree cleanup (см. Note 9)
- [ ] Отдельное сообщение если вызвано из topic

**Announcement:**
- [ ] Анонс команд после успешного запуска (по типу чата)

**Strings & Keyboards:**
- [ ] Константы в strings.py (URL validation, reset flow, buttons)
- [ ] `keyboards/reset.py` для reset flow

**Testing:**
- [ ] E2E тесты для error cases
- [ ] E2E тесты для concurrent /start
- [ ] E2E тесты для legacy project migration

## Implementation Notes

### 1. git_clone() cleanup при ошибке

**Проблема:** `project_launcher.git_clone()` не чистит директорию при ошибке.

**Решение:** Обновить `git_clone()` для cleanup:

```python
def git_clone(path: str, repo_url: str) -> LaunchResult:
    """Clone repository into path. Cleans up on failure."""
    target = Path(path)
    try:
        parent = str(target.parent)
        name = target.name
        result = subprocess.run(
            ["git", "clone", repo_url, name],
            cwd=parent,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Cleanup partial clone
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            return LaunchResult(success=False, error=f"git clone error: {result.stderr}")
        return LaunchResult(success=True)
    except Exception as e:
        # Cleanup on exception
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        return LaunchResult(success=False, error=str(e))
```

### 2. FSM retry для невалидного URL

**Проблема:** `FlowAction.ERROR` очищает FSM state, retry невозможен.

**Решение:** Новый action `ASK_CLONE_URL_RETRY` который показывает ошибку + prompt:

```python
class FlowAction(Enum):
    # ... existing
    ASK_CLONE_URL = "ask_clone_url"
    ASK_CLONE_URL_RETRY = "ask_clone_url_retry"  # NEW: shows error + re-prompt
```

В `handle_clone_url()`:
```python
is_valid, error_msg = validate_git_url(url)
if not is_valid:
    return FlowResult(
        action=FlowAction.ASK_CLONE_URL_RETRY,
        error=error_msg,
        project=project,
        path=path,
    )
```

В handler:
```python
case FlowAction.ASK_CLONE_URL_RETRY:
    # НЕ очищаем state - остаёмся в awaiting_clone_url
    await telegram_queue.reply(
        message,
        f"{result.error}\n\n{strings.START_CLONE_URL_PROMPT}",
    )
```

### 3. Concurrency: ProjectManager._save()

**Проблема:** `_save()` не thread-safe при параллельных /start.

**Решение:** File locking через `fcntl` (Linux) или `portalocker`:

```python
import fcntl

def _save(self) -> None:
    """Persist to disk with file locking."""
    config_path = get_config_path()

    with open(config_path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # Read current state
            current = json.load(f)
            # Update projects
            current["projects"] = self._serialize_projects()
            # Write back
            f.seek(0)
            f.truncate()
            json.dump(current, f, indent=2)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

**Альтернатива:** Использовать `filelock` library для кросс-платформенности.

### 4. URL validation: /blob/ edge case

**Проблема:** `/blob/` может быть легитимным именем папки в репозитории.

**Решение:** Проверяем паттерн GitHub URL более точно:

```python
def validate_git_url(url: str) -> tuple[bool, str | None]:
    # GitHub-specific patterns
    github_blob_pattern = re.compile(r'github\.com/[^/]+/[^/]+/blob/')
    github_tree_pattern = re.compile(r'github\.com/[^/]+/[^/]+/tree/')

    if "/wiki/" in url and "github.com" in url:
        return False, strings.GIT_URL_INVALID_WIKI
    if github_blob_pattern.search(url):
        return False, strings.GIT_URL_INVALID_BLOB
    if github_tree_pattern.search(url):
        return False, strings.GIT_URL_INVALID_BLOB
    if "gist.github.com" in url:
        return False, strings.GIT_URL_INVALID_GIST
    if not url.startswith(("https://", "git@", "ssh://")):
        return False, strings.GIT_URL_INVALID_FORMAT
    return True, None
```

### 5. is_setup_phase(): legacy projects

**Проблема:** Legacy проекты могут не иметь `threads[None]`, но иметь `project.session_id`.

**Решение:** Fallback на legacy fields:

```python
def is_setup_phase(project: Project) -> bool:
    """True if Claude never ran. Handles legacy projects."""
    # Check new threads structure
    main_thread = project.threads.get(None)
    if main_thread and main_thread.session_id:
        return False

    # Fallback: legacy session_id field
    if project.session_id:
        return False

    return True
```

### 6. /reset_all scope: project vs topic

**Уточнение:** `/reset_all` ресетит ВЕСЬ проект, не отдельный topic.

- В main chat: ресетит проект + все topics
- В topic: ресетит весь проект (не только этот topic)
- Для удаления отдельного topic: используй `/finish`

**Сообщение если вызвано из topic:**
```
`[?]` Reset entire project `{name}`?

This will disconnect Claude in all topics and clear settings.

[Continue] [Cancel]
```

### 7. Uncommitted changes detection

**Реализация:**

```python
def has_uncommitted_changes(path: str) -> bool:
    """Check for uncommitted changes (staged, unstaged, untracked)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False  # Can't check = assume clean
```

**Edge cases:**
- Corrupted .git → return False (не блокируем delete)
- Stashed changes → не детектим (stash это backup, не uncommitted)
- Untracked files → детектим (могут быть важны)

### 8. require_project_ready() vs /clear semantics

**Текущее поведение /clear:** работает если tmux exists (даже если Claude starting).

**Новое поведение с require_project_ready():** блокирует если Claude starting.

**Решение:** Разные уровни проверки:

```python
async def require_project_exists(message, telegram_queue) -> bool:
    """Basic check: project + cwd."""
    # ... minimal check

async def require_tmux_exists(message, telegram_queue) -> bool:
    """Check: project + cwd + tmux session exists."""
    # ... for /clear, /esc

async def require_claude_ready(message, telegram_queue) -> bool:
    """Strict check: project + cwd + tmux + Claude ready."""
    # ... for /new, /thread, /branch, /finish
```

**Mapping:**
- `/clear`, `/esc` → `require_tmux_exists()` (работают во время startup)
- `/new`, `/thread`, `/branch`, `/finish` → `require_claude_ready()`

### 9. Worktree cleanup в /reset_all

**/reset_all должен чистить worktrees:**

```python
def cleanup_project(project: Project, delete_directory: bool) -> None:
    """Full project cleanup."""
    # 1. Kill all tmux sessions (main + topics)
    for thread in project.threads.values():
        tmux_name = thread.get_tmux_session(project.project_name)
        if is_tmux_session_exists(tmux_name):
            kill_tmux_session(tmux_name)

    # 2. Remove worktrees (if any)
    if project.cwd:
        worktrees_dir = Path(project.cwd) / ".worktrees"
        for thread in project.threads.values():
            if thread.worktree_path:
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", thread.worktree_path],
                        cwd=project.cwd,
                        capture_output=True,
                    )
                except Exception:
                    pass  # Best effort

    # 3. Delete main directory (if requested)
    if delete_directory and project.cwd:
        shutil.rmtree(project.cwd, ignore_errors=True)

    # 4. Remove from config
    project_manager.remove(project.project_name)
```

### 10. unidecode: уже в зависимостях ✓

Проверено: `pyproject.toml` содержит `"unidecode>=1.3"`
