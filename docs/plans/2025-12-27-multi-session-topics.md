# Multi-Session Topics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable multiple parallel Claude sessions per project using Telegram Forum Topics.

**Architecture:** Each topic = separate tmux + Claude session. ThreadInfo stores per-thread state. Session binding matches by user message. Watcher and poller run per-thread.

**Tech Stack:** Python 3.12, aiogram 3.x, Telegram Bot API Forum Topics

---

## Этапы (для изолированного тестирования)

### Этап 1: Инфраструктура (Tasks 1-4, 4a)
**Что:** ThreadInfo, ProjectState.threads, config save/load, magic names
**Чекпоинт:** Task 4a — unit тесты должны пройти

### Этап 2: Команды (Tasks 5-6, 6a)
**Что:** `/session_new`, `/session_close`, `/start` в топике
**Чекпоинт:** Task 6a — ручное тестирование команд

### Этап 3: Message routing (Task 7, 7a)
**Что:** Роутинг сообщений по thread_id
**Чекпоинт:** Task 7a — проверка что сообщения идут в правильный tmux

### Этап 4: Session binding & watcher (Tasks 8-9, 9a)
**Что:** Привязка сессии, watcher для threads
**Чекпоинт:** Task 9a — полный цикл общения

### Этап 5: Permission poller (Task 10, 10a)
**Что:** Permission poller для threads
**Чекпоинт:** Task 10a — permissions в топике

### Этап 6: Lifecycle (Tasks 11-12, 12a)
**Что:** Migration, tmux died, /resume block
**Чекпоинт:** Task 12a — edge cases

---

## Task 1: Create ThreadInfo dataclass

**Files:**
- Modify: `src/telegram_bridge/session_manager.py:44-66`
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
# tests/test_session_manager.py
import pytest
from telegram_bridge.session_manager import ThreadInfo

def test_thread_info_creation():
    thread = ThreadInfo(thread_id=12345, name="mystic")
    assert thread.thread_id == 12345
    assert thread.name == "mystic"
    assert thread.session_id is None
    assert thread.jsonl_path is None

def test_thread_info_get_tmux_session_main():
    thread = ThreadInfo(thread_id=None, name="main")
    assert thread.get_tmux_session("codogram") == "claude-codogram"

def test_thread_info_get_tmux_session_named():
    thread = ThreadInfo(thread_id=12345, name="mystic")
    assert thread.get_tmux_session("codogram") == "claude-codogram-mystic"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py -v`
Expected: FAIL with "cannot import name 'ThreadInfo'"

**Step 3: Write minimal implementation**

Add to `src/telegram_bridge/session_manager.py` before ProjectState:

```python
@dataclass
class ThreadInfo:
    """State for a single thread (topic) within a project."""
    thread_id: int | None  # None = General topic
    name: str              # mystic, arcane, user-provided, or "main"

    # Runtime state (from history.jsonl):
    session_id: str | None = None
    jsonl_path: str | None = None

    # Tasks:
    watcher_task: asyncio.Task | None = field(default=None, repr=False)
    poller_task: asyncio.Task | None = field(default=None, repr=False)
    binding_task: asyncio.Task | None = field(default=None, repr=False)

    # For session binding:
    last_sent_message: str | None = None
    awaiting_new_session: bool = False

    def get_tmux_session(self, project_name: str) -> str:
        """Get tmux session name for this thread."""
        if self.name == "main":
            return f"claude-{project_name}"
        return f"claude-{project_name}-{self.name}"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/session_manager.py tests/test_session_manager.py
git commit -m "feat(telegram-bridge): add ThreadInfo dataclass"
```

---

## Task 2: Add threads dict to ProjectState

**Files:**
- Modify: `src/telegram_bridge/session_manager.py:44-66`
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
def test_project_state_has_threads():
    from telegram_bridge.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test")
    assert hasattr(project, 'threads')
    assert project.threads == {}

def test_project_state_get_thread():
    from telegram_bridge.session_manager import ProjectState, ThreadInfo
    project = ProjectState(project_name="test")
    thread = ThreadInfo(thread_id=None, name="main")
    project.threads[None] = thread
    assert project.get_thread(None) == thread
    assert project.get_thread(12345) is None

def test_project_state_get_or_create_thread():
    from telegram_bridge.session_manager import ProjectState
    project = ProjectState(project_name="test")
    thread = project.get_or_create_thread(None, "main")
    assert thread.name == "main"
    assert project.threads[None] == thread
    # Second call returns same thread
    thread2 = project.get_or_create_thread(None, "main")
    assert thread2 is thread
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_project_state_has_threads -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update ProjectState in `src/telegram_bridge/session_manager.py`:

```python
@dataclass
class ProjectState:
    """State for a single project."""
    project_name: str
    chat_id: int | None = None
    cwd: str | None = None

    # Multi-thread support: thread_id -> ThreadInfo
    threads: dict[int | None, ThreadInfo] = field(default_factory=dict)

    # Legacy fields (for migration, will be moved to ThreadInfo)
    session_id: str | None = None
    jsonl_path: str | None = None
    watcher_task: asyncio.Task | None = field(default=None, repr=False)
    tmux_session: str | None = None
    poller_task: asyncio.Task | None = field(default=None, repr=False)
    last_sent_message: str | None = None
    binding_task: asyncio.Task | None = field(default=None, repr=False)
    awaiting_new_session: bool = False

    def get_thread(self, thread_id: int | None) -> ThreadInfo | None:
        """Get thread by thread_id."""
        return self.threads.get(thread_id)

    def get_or_create_thread(self, thread_id: int | None, name: str) -> ThreadInfo:
        """Get existing thread or create new one."""
        if thread_id not in self.threads:
            self.threads[thread_id] = ThreadInfo(thread_id=thread_id, name=name)
        return self.threads[thread_id]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/session_manager.py tests/test_session_manager.py
git commit -m "feat(telegram-bridge): add threads dict to ProjectState"
```

---

## Task 3: Update config save/load for threads

**Files:**
- Modify: `src/telegram_bridge/session_manager.py:75-98`
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
def test_config_saves_threads(tmp_path, monkeypatch):
    from telegram_bridge.session_manager import ProjectManager, ThreadInfo
    from telegram_bridge import config

    config_file = tmp_path / ".config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", config_file)

    manager = ProjectManager()
    project = manager.get_or_create("test-project")
    project.chat_id = 123
    project.cwd = "/test/path"
    project.threads[None] = ThreadInfo(thread_id=None, name="main")
    project.threads[12345] = ThreadInfo(thread_id=12345, name="mystic")
    manager._save()

    # Reload and check
    import json
    saved = json.loads(config_file.read_text())
    assert "test-project" in saved["projects"]
    assert "threads" in saved["projects"]["test-project"]
    assert "null" in saved["projects"]["test-project"]["threads"]
    assert saved["projects"]["test-project"]["threads"]["null"]["name"] == "main"
    assert "12345" in saved["projects"]["test-project"]["threads"]

def test_config_loads_threads(tmp_path, monkeypatch):
    from telegram_bridge import config
    import json

    config_file = tmp_path / ".config.json"
    config_file.write_text(json.dumps({
        "projects": {
            "test-project": {
                "chat_id": 123,
                "cwd": "/test/path",
                "threads": {
                    "null": {"name": "main"},
                    "12345": {"name": "mystic"}
                }
            }
        }
    }))
    monkeypatch.setattr(config, "CONFIG_PATH", config_file)

    from telegram_bridge.session_manager import ProjectManager
    manager = ProjectManager()
    project = manager.projects.get("test-project")
    assert project is not None
    assert None in project.threads
    assert project.threads[None].name == "main"
    assert 12345 in project.threads
    assert project.threads[12345].name == "mystic"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_config_saves_threads -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update `_save` method:

```python
def _save(self) -> None:
    """Persist to disk."""
    projects_data = {}
    for name, p in self.projects.items():
        if p.chat_id is None:
            continue
        project_data = {"chat_id": p.chat_id, "cwd": p.cwd}
        if p.threads:
            project_data["threads"] = {
                str(tid) if tid is not None else "null": {"name": t.name}
                for tid, t in p.threads.items()
            }
        projects_data[name] = project_data
    self._config["projects"] = projects_data
    self._config.pop("sessions", None)
    save_config(self._config)
```

Update `_load_projects` method:

```python
def _load_projects(self) -> None:
    """Load projects from config."""
    saved_projects = self._config.get("projects", {})
    for project_name, data in saved_projects.items():
        project = ProjectState(project_name=project_name)
        if isinstance(data, int):
            project.chat_id = data
        else:
            project.chat_id = data.get("chat_id")
            project.cwd = data.get("cwd")
            # Load threads
            threads_data = data.get("threads", {})
            for tid_str, thread_data in threads_data.items():
                tid = None if tid_str == "null" else int(tid_str)
                project.threads[tid] = ThreadInfo(
                    thread_id=tid,
                    name=thread_data.get("name", "main")
                )
        self.projects[project_name] = project
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/session_manager.py tests/test_session_manager.py
git commit -m "feat(telegram-bridge): save/load threads in config"
```

---

## Task 4: Add MAGIC_NAMES for thread naming

**Files:**
- Create: `src/telegram_bridge/magic_names.py`
- Test: `tests/test_magic_names.py`

**Step 1: Write the failing test**

```python
# tests/test_magic_names.py
def test_get_random_magic_name():
    from telegram_bridge.magic_names import get_random_magic_name
    name = get_random_magic_name()
    assert isinstance(name, str)
    assert len(name) > 0

def test_get_random_magic_name_excludes():
    from telegram_bridge.magic_names import get_random_magic_name, MAGIC_NAMES
    # Exclude all but one
    excluded = set(MAGIC_NAMES[:-1])
    name = get_random_magic_name(excluded)
    assert name == MAGIC_NAMES[-1]

def test_get_random_magic_name_all_excluded_returns_uuid():
    from telegram_bridge.magic_names import get_random_magic_name, MAGIC_NAMES
    excluded = set(MAGIC_NAMES)
    name = get_random_magic_name(excluded)
    # Should be a short UUID-like string
    assert len(name) == 8
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_magic_names.py -v`
Expected: FAIL with "No module named 'telegram_bridge.magic_names'"

**Step 3: Write minimal implementation**

Create `src/telegram_bridge/magic_names.py`:

```python
"""Magic names for thread naming."""
import random
import uuid

MAGIC_NAMES = [
    "arcane", "mystic", "ethereal", "celestial", "phantom",
    "cosmic", "astral", "enigmatic", "luminous", "spectral",
    "sublime", "radiant", "obscure", "cryptic", "eldritch",
    "prismatic", "nebulous", "transcendent", "immortal", "mythic",
    "ancient", "eternal", "infinite", "quantum", "stellar",
    "lunar", "solar", "void", "nexus", "apex",
]


def get_random_magic_name(excluded: set[str] | None = None) -> str:
    """Get a random magic name not in excluded set."""
    excluded = excluded or set()
    available = [n for n in MAGIC_NAMES if n not in excluded]
    if not available:
        return uuid.uuid4().hex[:8]
    return random.choice(available)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_magic_names.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/telegram_bridge/magic_names.py tests/test_magic_names.py
git commit -m "feat(telegram-bridge): add magic names for threads"
```

---

## Task 4a: Checkpoint — Unit tests

**Инструкция для ручного тестирования:**

1. Запустить unit тесты:
```bash
cd agent-tools/telegram-bridge
pytest tests/test_session_manager.py tests/test_magic_names.py -v
```

2. Все тесты должны пройти (зелёные)

3. Проверить что тесты покрывают:
   - ThreadInfo создание и get_tmux_session
   - ProjectState.threads, get_thread, get_or_create_thread
   - Сохранение/загрузка threads в config
   - Magic names: get_random_magic_name, excludes, UUID fallback

**Критерий успеха:** Все тесты зелёные, pytest exit code 0

---

## Task 5: Add /session_new command and /start in topic support

**Files:**
- Modify: `src/telegram_bridge/bot.py`
- Test: manual testing (Telegram commands hard to unit test)

**Step 1: Add helper function for launching Claude in thread**

```python
async def launch_claude_in_thread(
    message: Message,
    project: ProjectState,
    thread: ThreadInfo,
    start_poller,
    start_watcher,
):
    """Launch Claude for a specific thread."""
    tmux_name = thread.get_tmux_session(project.project_name)

    # Create tmux session
    from .tmux import create_tmux_with_claude
    result = create_tmux_with_claude(tmux_name, project.cwd)
    if not result.success:
        await message.answer(f"Ошибка запуска Claude: {result.error}")
        return False

    # Doom-guy animation (same as launch_claude_new)
    # ... animation code ...

    await message.answer(
        f"🚀 Claude запущен в `{tmux_name}`\n"
        f"Подключиться: `tmux attach -t {tmux_name}`",
        parse_mode="Markdown"
    )
    return True
```

**Step 2: Update /start to work in topics**

In the existing `/start` handler, add thread support:

```python
@router.message(Command("start"))
async def on_start(message: Message):
    # ... existing code ...

    thread_id = message.message_thread_id

    # If in a topic, check for pending thread
    if thread_id is not None:
        project = project_manager.get_by_chat(chat_id)
        if project:
            thread = project.threads.get(thread_id)
            if thread and thread.name == "pending":
                # Upgrade pending thread
                from .magic_names import get_random_magic_name
                existing_names = {t.name for t in project.threads.values() if t.name != "pending"}
                thread.name = get_random_magic_name(existing_names)

                start_poller, start_watcher = _make_task_starters(message.bot)
                await launch_claude_in_thread(message, project, thread, start_poller, start_watcher)
                project_manager._save()
                return

    # ... rest of existing /start logic for project registration ...
```

**Step 3: Add /session_new command**

```python
@router.message(Command("session_new"))
async def on_session_new(message: Message):
    """Create a new thread (topic) with its own Claude session."""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("Проект не найден. Сначала используй /start")
        return

    # Check if chat supports topics
    chat = await message.bot.get_chat(chat_id)
    if not chat.is_forum:
        await message.answer("Этот чат не поддерживает топики. Включите Topics в настройках группы.")
        return

    # Parse optional name from command
    from .magic_names import get_random_magic_name
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        name = args[1].strip().lower()
        # Validate name
        if not name.replace("-", "").replace("_", "").isalnum():
            await message.answer("Имя должно содержать только буквы, цифры, - и _")
            return
    else:
        # Get existing thread names to exclude
        existing_names = {t.name for t in project.threads.values() if t.name != "pending"}
        name = get_random_magic_name(existing_names)

    # Check if name already exists
    for thread in project.threads.values():
        if thread.name == name:
            await message.answer(f"Тред с именем '{name}' уже существует")
            return

    # Create Telegram topic
    try:
        topic = await message.bot.create_forum_topic(chat_id, name.capitalize())
    except Exception as e:
        await message.answer(f"Ошибка создания топика: {e}")
        return

    # Create ThreadInfo
    thread = ThreadInfo(thread_id=topic.message_thread_id, name=name)
    project.threads[topic.message_thread_id] = thread

    # Launch Claude
    start_poller, start_watcher = _make_task_starters(message.bot)
    success = await launch_claude_in_thread(
        message, project, thread, start_poller, start_watcher
    )

    if success:
        project_manager._save()
```

**Step 2: Register command in bot menu**

Add to menu in `main.py` or bot setup:

```python
BotCommand(command="session_new", description="Create new Claude thread"),
```

**Step 3: Test manually**

1. Create a supergroup with Topics enabled
2. Add bot as admin with "Manage Topics" permission
3. Run `/session_new` - should create topic with magic name
4. Run `/session_new myname` - should create topic "myname"

**Step 4: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): add /session_new command"
```

---

## Task 6: Add /session_close command

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add command handler**

```python
@router.message(Command("session_close"))
async def on_session_close(message: Message):
    """Close current thread and its Claude session."""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id

    if thread_id is None:
        await message.answer("Эту команду можно использовать только в топике")
        return

    project = project_manager.get_by_chat(chat_id)
    if not project:
        await message.answer("Проект не найден")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("Этот топик не связан с Claude сессией")
        return

    # Confirmation
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, закрыть", callback_data=f"session_close:{thread_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="session_close:cancel"),
        ]
    ])
    await message.answer(
        f"Закрыть тред '{thread.name}'?\n"
        "Топик и tmux сессия будут удалены.",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("session_close:"))
async def on_session_close_callback(callback: CallbackQuery):
    """Handle thread close confirmation."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Not authorized")
        return

    data = callback.data.split(":")[1]
    if data == "cancel":
        await callback.message.edit_text("Отменено")
        await callback.answer()
        return

    thread_id = int(data)
    chat_id = callback.message.chat.id
    project = project_manager.get_by_chat(chat_id)
    if not project:
        await callback.answer("Проект не найден")
        return

    thread = project.threads.get(thread_id)
    if not thread:
        await callback.answer("Тред не найден")
        return

    # Stop tasks
    if thread.watcher_task:
        thread.watcher_task.cancel()
    if thread.poller_task:
        thread.poller_task.cancel()
    if thread.binding_task:
        thread.binding_task.cancel()

    # Kill tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    import subprocess
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Delete topic
    try:
        await callback.bot.delete_forum_topic(chat_id, thread_id)
    except Exception as e:
        await callback.message.edit_text(f"Ошибка удаления топика: {e}")
        await callback.answer()
        return

    # Remove from project
    del project.threads[thread_id]
    project_manager._save()

    await callback.answer("Тред закрыт")
```

**Step 2: Test manually**

1. Create thread with `/session_new`
2. In that thread run `/session_close`
3. Confirm - topic should be deleted

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): add /session_close command"
```

---

## Task 6a: Checkpoint — Commands manual test

**Инструкция для ручного тестирования:**

**Подготовка:**
1. Создать Telegram supergroup с включёнными Topics
2. Добавить бота как админа с правами "Manage Topics"
3. Зарегистрировать проект через `/start`

**Тест /session_new:**
1. В группе выполнить `/session_new`
   - Ожидание: создаётся новый топик с magic name (arcane/mystic/etc)
   - Ожидание: запускается tmux с Claude
   - Ожидание: doom-guy анимация, затем "Ready!"

2. В группе выполнить `/session_new mytest`
   - Ожидание: создаётся топик "Mytest"
   - Ожидание: tmux session = `claude-<project>-mytest`

3. Попробовать `/session_new invalid@name`
   - Ожидание: ошибка про допустимые символы

**Тест /start в топике:**
1. Создать топик вручную через Telegram UI
2. Написать любое сообщение в нём
   - Ожидание: бот отвечает "Используй /start или /session_new..."
3. Выполнить `/start` в этом топике
   - Ожидание: pending thread апгрейдится, запускается Claude

**Тест /session_close:**
1. В созданном топике выполнить `/session_close`
   - Ожидание: кнопки подтверждения
2. Нажать "Да, закрыть"
   - Ожидание: топик удаляется, tmux session убивается

**Критерий успеха:** Все сценарии работают без ошибок

---

## Task 7: Update message routing for thread_id

**Files:**
- Modify: `src/telegram_bridge/bot.py:799-850` (on_message handler)

**Step 1: Update on_message handler**

Replace the existing on_message handler to route by thread_id:

```python
@router.message()
async def on_message(message: Message):
    """Handle regular messages."""
    if not is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread_id = message.message_thread_id  # None for General topic

    # Skip commands
    if message.text and message.text.startswith("/"):
        return

    # Handle /start flow state
    if chat_id in _start_state:
        state = _start_state[chat_id]
        if state.get("state") == "awaiting_project_name":
            await handle_project_name(message)
            return
        elif state.get("state") == "awaiting_custom_path":
            await handle_custom_path(message)
            return
        elif state.get("state") == "awaiting_repo_url":
            await handle_repo_url(message)
            return

    project = project_manager.get_by_chat(chat_id)
    if not project:
        return

    # Get or create thread for this topic
    thread = project.threads.get(thread_id)
    if not thread:
        if thread_id is None:
            # Legacy: use project-level fields for General topic
            # This maintains backward compatibility
            pass
        else:
            # Unknown topic - create pending ThreadInfo, show hint once
            thread = ThreadInfo(thread_id=thread_id, name="pending")
            project.threads[thread_id] = thread
            project_manager._save()
            await message.answer("Используй /start или /session_new для подключения Claude к этому топику")
            return

    # Skip pending threads (no tmux yet)
    if thread.name == "pending":
        return

    start_poller, start_watcher = _make_task_starters(message.bot)

    # Session binding logic
    if thread:
        # Multi-thread mode: use ThreadInfo
        tmux_name = thread.get_tmux_session(project.project_name)

        if thread.session_id is None:
            from .history_watcher import poll_for_session_thread
            thread.last_sent_message = message.text
            if not thread.binding_task or thread.binding_task.done():
                thread.binding_task = asyncio.create_task(
                    poll_for_session_thread(project, thread, message.bot, start_poller, start_watcher)
                )
        else:
            from .history_watcher import check_session_for_thread
            await check_session_for_thread(project, thread, message.bot, start_poller, start_watcher)
    else:
        # Legacy single-thread mode (General topic without ThreadInfo)
        if project.session_id is None:
            from .history_watcher import poll_for_session
            project.last_sent_message = message.text
            if not project.binding_task or project.binding_task.done():
                project.binding_task = asyncio.create_task(
                    poll_for_session(project, message.bot, start_poller, start_watcher)
                )
        else:
            from .history_watcher import check_session_for_project
            await check_session_for_project(project, message.bot, start_poller, start_watcher)

    # Send to tmux
    if thread:
        tmux = TmuxSession(thread.get_tmux_session(project.project_name), project.cwd)
    else:
        tmux = get_session_for_chat(chat_id)

    if tmux:
        tmux.send_message(message.text)
```

**Step 2: Test manually**

1. Send message in General topic - should work as before
2. Create thread with `/session_new`
3. Send message in that thread - should go to thread's tmux

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): route messages by thread_id"
```

---

## Task 7a: Checkpoint — Message routing test

**Инструкция для ручного тестирования:**

**Подготовка:**
- Иметь группу с минимум 2 топиками + General

**Тест изоляции сообщений:**
1. Открыть `tmux attach -t claude-<project>-<topic1>` в одном терминале
2. Открыть `tmux attach -t claude-<project>-<topic2>` в другом терминале
3. Отправить "test1" в topic1 в Telegram
   - Ожидание: "test1" появляется только в tmux topic1
4. Отправить "test2" в topic2 в Telegram
   - Ожидание: "test2" появляется только в tmux topic2
5. Отправить "test3" в General topic
   - Ожидание: идёт в legacy project tmux (если есть) или игнорируется

**Тест pending thread:**
1. Создать новый топик вручную (не через /session_new)
2. Написать сообщение
   - Ожидание: "Используй /start или /session_new..."
3. Написать ещё сообщение
   - Ожидание: тишина (pending thread игнорирует сообщения)

**Критерий успеха:** Сообщения идут в правильные tmux сессии

---

## Task 8: Add thread-aware session binding

**Files:**
- Modify: `src/telegram_bridge/history_watcher.py`

**Step 1: Add poll_for_session_thread function**

```python
async def poll_for_session_thread(
    project: ProjectState,
    thread: ThreadInfo,
    bot: Bot,
    start_poller,
    start_watcher,
) -> None:
    """Poll for a session that matches thread.last_sent_message."""
    if not project.cwd or not thread.last_sent_message:
        logger.warning("poll_for_session_thread: missing cwd or last_sent_message")
        return

    old_session_id = thread.session_id
    start_time = time.time()

    logger.info("poll_for_session_thread_start", extra={
        "project": project.project_name,
        "thread": thread.name,
        "looking_for": thread.last_sent_message[:30] if thread.last_sent_message else None,
    })

    while time.time() - start_time < BINDING_TIMEOUT:
        try:
            latest_session_id = find_session_for_project(project.cwd)

            if latest_session_id and latest_session_id != old_session_id:
                jsonl_path = compute_jsonl_path(project.cwd, latest_session_id)

                if jsonl_path.exists():
                    last_user_msg = get_last_user_message_from_jsonl(jsonl_path)

                    if last_user_msg == thread.last_sent_message:
                        logger.info("session_bound_thread", extra={
                            "project": project.project_name,
                            "thread": thread.name,
                            "session_id": latest_session_id[:8],
                        })

                        thread.session_id = latest_session_id
                        thread.jsonl_path = str(jsonl_path)
                        thread.awaiting_new_session = False

                        # Start thread-specific watcher
                        if not thread.watcher_task or thread.watcher_task.done():
                            thread.watcher_task = asyncio.create_task(
                                watch_thread_jsonl(bot, project, thread)
                            )
                        return

        except Exception as e:
            logger.warning("poll_for_session_thread_error", extra={"error": str(e)})

        await asyncio.sleep(BINDING_INTERVAL)

    # Timeout
    logger.warning("poll_for_session_thread_timeout", extra={
        "project": project.project_name,
        "thread": thread.name,
    })
    thread.awaiting_new_session = False
    try:
        await bot.send_message(
            project.chat_id,
            "⚠️ Сессия не обнаружена. Проверьте что Claude запущен.",
            message_thread_id=thread.thread_id
        )
    except Exception:
        pass
```

**Step 2: Add check_session_for_thread function**

```python
async def check_session_for_thread(
    project: ProjectState,
    thread: ThreadInfo,
    bot: Bot,
    start_poller,
    start_watcher,
) -> None:
    """Check if session changed for a thread."""
    if not project.cwd:
        return

    old_session = thread.session_id
    new_session_id = find_session_for_project(project.cwd)

    if new_session_id and new_session_id != old_session:
        # Session changed - user did /new or /compact
        logger.info("session_changed_thread", extra={
            "project": project.project_name,
            "thread": thread.name,
            "old_session": old_session[:8] if old_session else None,
            "new_session": new_session_id[:8],
        })

        # Reset and wait for binding
        thread.session_id = None
        thread.jsonl_path = None
        if thread.watcher_task:
            thread.watcher_task.cancel()
            thread.watcher_task = None
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/history_watcher.py
git commit -m "feat(telegram-bridge): add thread-aware session binding"
```

---

## Task 9: Add thread-specific watcher

**Files:**
- Modify: `src/telegram_bridge/history_watcher.py`
- Modify: `src/telegram_bridge/watcher.py`

**Step 1: Add watch_thread_jsonl function**

```python
async def watch_thread_jsonl(bot: Bot, project: ProjectState, thread: ThreadInfo):
    """Watch jsonl for a specific thread and send messages to that thread."""
    from .watcher import JsonlWatcher, send_entry_to_telegram

    if not thread.jsonl_path:
        return

    watcher = JsonlWatcher(Path(thread.jsonl_path))

    async for entry in watcher.watch():
        try:
            await send_entry_to_telegram(
                bot,
                project.chat_id,
                entry,
                message_thread_id=thread.thread_id
            )
        except Exception as e:
            logger.error("watch_thread_error", extra={"error": str(e)})
```

**Step 2: Update send_entry_to_telegram to accept thread_id**

In `src/telegram_bridge/watcher.py`, update function signature:

```python
async def send_entry_to_telegram(
    bot: Bot,
    chat_id: int,
    entry: ParsedEntry,
    message_thread_id: int | None = None,
):
    """Send parsed entry to Telegram chat."""
    # ... existing code ...
    await bot.send_message(
        chat_id,
        formatted_text,
        parse_mode="Markdown",
        message_thread_id=message_thread_id,  # Add this
    )
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/history_watcher.py src/telegram_bridge/watcher.py
git commit -m "feat(telegram-bridge): add thread-specific watcher"
```

---

## Task 9a: Checkpoint — Full conversation cycle

**Инструкция для ручного тестирования:**

**Тест полного цикла в топике:**
1. Создать топик через `/session_new`
2. Дождаться "Ready!"
3. Написать простой запрос: "Say hello"
4. Ожидание:
   - Сообщение уходит в tmux (видно в attach)
   - Claude отвечает
   - Ответ появляется в Telegram в том же топике
5. Написать ещё запрос: "What's 2+2?"
   - Ожидание: ответ появляется в этом же топике

**Тест session binding:**
1. В другом топике (без Claude) написать сообщение
2. Затем создать там Claude через `/start`
3. Написать "test binding"
   - Ожидание: session_id привязывается, watcher запускается

**Тест смены сессии (/new):**
1. В tmux выполнить `/new` (новая Claude сессия)
2. В Telegram написать сообщение
   - Ожидание: session rebinding происходит автоматически
   - Ожидание: новый watcher запускается

**Критерий успеха:** Полный цикл общения работает в каждом топике независимо

---

## Task 10: Add thread-specific permission poller

**Files:**
- Modify: `src/telegram_bridge/permission_poller.py`

**Step 1: Update start_poller to accept thread**

Update the permission poller to send messages to the correct thread:

```python
async def start_permission_poller_for_thread(
    project: ProjectState,
    thread: ThreadInfo,
    bot: Bot,
) -> asyncio.Task:
    """Start permission poller for a specific thread."""
    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    async def poll_loop():
        while True:
            try:
                output = tmux.capture_pane()
                if has_permission_prompt(output):
                    options = parse_permission_options(output)
                    keyboard = create_permission_keyboard(options, project.project_name)
                    await bot.send_message(
                        project.chat_id,
                        format_permission_prompt(output),
                        reply_markup=keyboard,
                        message_thread_id=thread.thread_id,  # Send to thread
                    )
            except Exception as e:
                logger.error("permission_poll_error", extra={"error": str(e)})
            await asyncio.sleep(1)

    return asyncio.create_task(poll_loop())
```

**Step 2: Update on_permission_callback to find thread**

The callback handler needs to find which thread the permission belongs to:

```python
@router.callback_query(F.data.startswith("perm:"))
async def on_permission_callback(callback: CallbackQuery):
    # ... existing code ...
    thread_id = callback.message.message_thread_id

    project = project_manager.get_by_chat(chat_id)
    if not project:
        return

    # Find tmux session - check thread first, then project
    if thread_id and thread_id in project.threads:
        thread = project.threads[thread_id]
        tmux_name = thread.get_tmux_session(project.project_name)
    else:
        tmux_name = project.tmux_session

    # Send response to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_message(response)
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/permission_poller.py src/telegram_bridge/bot.py
git commit -m "feat(telegram-bridge): add thread-specific permission poller"
```

---

## Task 10a: Checkpoint — Permissions in topics

**Инструкция для ручного тестирования:**

**Тест permission prompt в топике:**
1. Создать топик через `/session_new`
2. Попросить Claude сделать что-то требующее разрешения:
   ```
   Create a file test.txt with content "hello"
   ```
3. Ожидание:
   - Permission prompt появляется В ЭТОМ ЖЕ топике
   - Кнопки Yes/No работают
   - После нажатия Yes файл создаётся
   - Сообщение с кнопками удаляется

**Тест изоляции permissions:**
1. Открыть два топика с Claude
2. В первом попросить создать файл
3. Убедиться что permission приходит только в первый топик
4. Во втором попросить создать другой файл
5. Убедиться что permission приходит только во второй топик

**Критерий успеха:** Permissions работают изолированно в каждом топике

---

## Task 11: Migration and thread lifecycle management

**Files:**
- Modify: `src/telegram_bridge/session_manager.py`
- Modify: `src/telegram_bridge/history_watcher.py`

**Step 1: Update restore_projects for migration**

Add migration logic to create "main" thread for existing projects:

```python
async def restore_projects(self, bot, start_poller, start_watcher) -> None:
    """Restore sessions from history.jsonl after bot restart."""
    # ... existing code ...

    for project in list(self.projects.values()):
        # ... existing restore logic ...

        # Migration: create main thread if project has no threads
        if not project.threads and project.tmux_session:
            main_thread = ThreadInfo(thread_id=None, name="main")
            # Copy legacy fields to main thread
            main_thread.session_id = project.session_id
            main_thread.jsonl_path = project.jsonl_path
            project.threads[None] = main_thread
            logger.info("migrated_to_threads", extra={"project": project.project_name})

        # Restore watcher/poller for each thread
        for thread in project.threads.values():
            tmux_name = thread.get_tmux_session(project.project_name)
            tmux = TmuxSession(tmux_name, project.cwd)

            if not tmux.exists():
                continue  # Skip dead tmux

            # Start poller for this thread
            if not thread.poller_task or thread.poller_task.done():
                thread.poller_task = await start_poller_for_thread(project, thread, bot)

            # Start watcher if session bound
            if thread.session_id and thread.jsonl_path:
                if not thread.watcher_task or thread.watcher_task.done():
                    thread.watcher_task = asyncio.create_task(
                        watch_thread_jsonl(bot, project, thread)
                    )

        # ... rest of restore logic ...
```

**Step 2: Add tmux died detection for threads**

In `HistoryWatcher._check_for_changes`, add thread health check:

```python
async def _check_for_changes(self):
    # ... existing project checks ...

    # Check thread health
    for thread in list(project.threads.values()):
        tmux_name = thread.get_tmux_session(project.project_name)
        tmux = TmuxSession(tmux_name, project.cwd)

        if not tmux.exists():
            logger.warning("thread_tmux_died", extra={
                "project": project.project_name,
                "thread": thread.name
            })

            # Stop thread tasks
            if thread.watcher_task:
                thread.watcher_task.cancel()
                thread.watcher_task = None
            if thread.poller_task:
                thread.poller_task.cancel()
                thread.poller_task = None

            # Notify user
            try:
                await self.bot.send_message(
                    project.chat_id,
                    f"⚠️ Claude session closed: {thread.name}",
                    message_thread_id=thread.thread_id
                )
            except Exception:
                pass

            # Reset thread state
            thread.session_id = None
            thread.jsonl_path = None
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/session_manager.py src/telegram_bridge/history_watcher.py
git commit -m "feat(telegram-bridge): add thread lifecycle management"
```

---

## Task 12: Block /resume command

**Files:**
- Modify: `src/telegram_bridge/bot.py`

**Step 1: Add /resume detection**

When user sends message and we detect `/resume` was used in tmux (session has old history), show error:

```python
# In poll_for_session_thread, after finding session but message doesn't match:
# Check if this might be a /resume (session has multiple user messages already)

def is_likely_resume(jsonl_path: Path) -> bool:
    """Check if session looks like a /resume (has old history)."""
    user_msg_count = 0
    try:
        with open(jsonl_path, 'r') as f:
            for line in f:
                if '"type":"user"' in line:
                    user_msg_count += 1
                    if user_msg_count > 1:
                        return True
    except Exception:
        pass
    return False
```

**Step 2: Show error in poll_for_session_thread**

```python
async def poll_for_session_thread(...):
    # ... existing polling logic ...

    # After timeout, before showing generic error:
    if latest_session_id:
        jsonl_path = compute_jsonl_path(project.cwd, latest_session_id)
        if is_likely_resume(jsonl_path):
            await bot.send_message(
                project.chat_id,
                "⚠️ /resume не поддерживается в мультисессионном режиме.\n"
                "Используйте /new для новой сессии.",
                message_thread_id=thread.thread_id
            )
            return

    # ... generic timeout error ...
```

**Step 3: Commit**

```bash
git add src/telegram_bridge/bot.py src/telegram_bridge/history_watcher.py
git commit -m "feat(telegram-bridge): block /resume with error message"
```

---

## Task 12a: Checkpoint — Edge cases

**Инструкция для ручного тестирования:**

**Тест migration (legacy → threads):**
1. Иметь старый проект БЕЗ threads в .config.json
2. Перезапустить бота
3. Проверить .config.json
   - Ожидание: появился `threads: { "null": { "name": "main" } }`
4. Написать сообщение в General topic
   - Ожидание: работает как раньше

**Тест tmux died:**
1. Создать топик через `/session_new`
2. Дождаться Ready
3. Убить tmux вручную: `tmux kill-session -t claude-<project>-<name>`
4. Ожидание: в топике появляется "⚠️ Claude session closed: <name>"
5. Написать сообщение
   - Ожидание: предложение использовать /start или /session_new

**Тест /resume блокировки:**
1. В tmux выполнить `/resume` для старой сессии
2. Написать сообщение в Telegram
   - Ожидание: через timeout появляется сообщение про /resume
   - Ожидание: "⚠️ /resume не поддерживается..."

**Тест restore после рестарта бота:**
1. Создать 2-3 топика с активными Claude сессиями
2. Перезапустить бота (`./restart.sh`)
3. Написать сообщение в каждый топик
   - Ожидание: все сессии восстановились, ответы приходят

**Критерий успеха:** Все edge cases обрабатываются корректно

---

## Summary

18 tasks total (12 implementation + 6 checkpoints):

**Stage 1: Infrastructure (Tasks 1-4, 4a)**
1. ThreadInfo dataclass
2. Add threads dict to ProjectState
3. Config save/load for threads
4. Magic names for thread naming
4a. ✅ Checkpoint — Unit tests

**Stage 2: Commands (Tasks 5-6, 6a)**
5. /session_new command and /start in topic
6. /session_close command
6a. ✅ Checkpoint — Commands manual test

**Stage 3: Message routing (Task 7, 7a)**
7. Message routing by thread_id
7a. ✅ Checkpoint — Message routing test

**Stage 4: Session binding & watcher (Tasks 8-9, 9a)**
8. Thread-aware session binding
9. Thread-specific watcher
9a. ✅ Checkpoint — Full conversation cycle

**Stage 5: Permission poller (Task 10, 10a)**
10. Thread-specific permission poller
10a. ✅ Checkpoint — Permissions in topics

**Stage 6: Lifecycle (Tasks 11-12, 12a)**
11. Migration and thread lifecycle management
12. Block /resume command
12a. ✅ Checkpoint — Edge cases

Each task is atomic and can be committed separately. Checkpoints require user manual testing before proceeding to next stage.
