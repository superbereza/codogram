# Missed Responses Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** При смене сессии подхватывать пропущенные ответы Claude из jsonl файла.

**Architecture:** Добавляем параметр `send_missed` в watcher, который при `True` сначала читает jsonl, находит entries после последнего user message и отправляет их, затем продолжает слежение. Таймаут 5 минут для ошибки.

**Tech Stack:** Python, aiogram, asyncio

---

### Task 1: Функция find_missed_entries в watcher.py

**Files:**
- Modify: `src/codogram/watcher.py`
- Test: `tests/test_watcher.py`

**Step 1: Write the failing test**

```python
# tests/test_watcher.py
import json
import tempfile
from pathlib import Path
from codogram.watcher import find_missed_entries, ParsedEntry, ContentType


def test_find_missed_entries_returns_entries_after_last_user():
    """Should return all assistant entries after last user message."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({"type": "user", "message": {"content": []}}) + '\n')
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}) + '\n')
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}}) + '\n')
        path = Path(f.name)

    entries = find_missed_entries(path)

    assert len(entries) == 2
    assert entries[0].content_type == ContentType.TEXT
    assert entries[1].content_type == ContentType.TOOL_USE

    path.unlink()


def test_find_missed_entries_resets_on_new_user_message():
    """Should only return entries after the LAST user message."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({"type": "user", "message": {"content": []}}) + '\n')
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "First"}]}}) + '\n')
        f.write(json.dumps({"type": "user", "message": {"content": []}}) + '\n')
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Second"}]}}) + '\n')
        path = Path(f.name)

    entries = find_missed_entries(path)

    assert len(entries) == 1
    assert entries[0].text == "Second"

    path.unlink()


def test_find_missed_entries_empty_file():
    """Should return empty list for empty file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        path = Path(f.name)

    entries = find_missed_entries(path)

    assert entries == []

    path.unlink()


def test_find_missed_entries_file_not_exists():
    """Should return empty list if file doesn't exist."""
    path = Path("/nonexistent/file.jsonl")

    entries = find_missed_entries(path)

    assert entries == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_watcher.py -v -k "find_missed"`
Expected: FAIL with "cannot import name 'find_missed_entries'"

**Step 3: Write implementation**

Add to `src/codogram/watcher.py`:

```python
def find_missed_entries(path: Path) -> list[ParsedEntry]:
    """Find all assistant entries after last user message."""
    if not path.exists():
        return []

    try:
        entries = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("type") == "user":
                    entries = []  # reset after each user message
                else:
                    parsed = parse_jsonl_entry(entry)
                    if parsed:
                        entries.append(parsed)
        return entries
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"find_missed_entries error: {e}")
        return []
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_watcher.py -v -k "find_missed"`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/codogram/watcher.py tests/test_watcher.py
git commit -m "feat(watcher): add find_missed_entries function"
```

---

### Task 2: Параметр send_missed в create_watcher_task и watcher_for_session

**Files:**
- Modify: `src/codogram/watcher.py`

**Step 1: Update create_watcher_task signature**

```python
async def create_watcher_task(bot: Bot, project: ProjectState,
                              send_missed: bool = False) -> asyncio.Task:
    """Create watcher task for project."""
    return asyncio.create_task(watcher_for_session(bot, project, send_missed))
```

**Step 2: Update watcher_for_session to accept and use send_missed**

```python
async def watcher_for_session(bot: Bot, project: ProjectState,
                              send_missed: bool = False):
    """Watch jsonl for specific project."""
    if not project.jsonl_path:
        logger.warning(f"Watcher: no jsonl_path for project {project.project_name}")
        return

    path = Path(project.jsonl_path)
    chat_id = project.chat_id

    logger.info(f"Watcher started: watching {path} for chat {chat_id}")

    # Send missed entries if requested
    if send_missed and path.exists():
        missed = find_missed_entries(path)
        if missed:
            logger.info(f"Sending {len(missed)} missed entries for {project.project_name}")
            for entry in missed:
                try:
                    if entry.content_type == ContentType.TEXT:
                        for chunk in chunk_message(entry.text):
                            try:
                                await bot.send_message(chat_id, f"● {chunk}", parse_mode="Markdown")
                            except Exception:
                                await bot.send_message(chat_id, f"● {chunk}")

                    elif entry.content_type == ContentType.TOOL_USE:
                        text = format_tool_use(entry.tool_name, entry.tool_input)
                        try:
                            await bot.send_message(chat_id, text, parse_mode="Markdown")
                        except Exception:
                            await bot.send_message(chat_id, f"● {entry.tool_name}")
                except Exception as e:
                    logger.warning(f"Error sending missed entry: {e}")

    async for entry in watch_jsonl(path):
        # ... existing code unchanged ...
```

**Step 3: Run existing tests**

Run: `pytest tests/test_watcher.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/codogram/watcher.py
git commit -m "feat(watcher): add send_missed parameter to watcher functions"
```

---

### Task 3: Прокинуть send_missed через session_manager

**Files:**
- Modify: `src/codogram/session_manager.py`

**Step 1: Update _maybe_start_tasks signature**

Find `_maybe_start_tasks` method and update:

```python
async def _maybe_start_tasks(self, project: ProjectState, start_poller, start_watcher,
                             send_missed: bool = False) -> None:
    """Start tasks if all required data is present."""
    # Poller: needs tmux_session + chat_id
    if project.tmux_session and project.chat_id:
        if not project.poller_task or project.poller_task.done():
            project.poller_task = await start_poller(project)

    # Watcher: needs jsonl_path + chat_id
    if project.jsonl_path and project.chat_id:
        if not project.watcher_task or project.watcher_task.done():
            project.watcher_task = await start_watcher(project, send_missed)
```

**Step 2: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(session_manager): add send_missed parameter to _maybe_start_tasks"
```

---

### Task 4: Передать send_missed=True при смене сессии в history_watcher

**Files:**
- Modify: `src/codogram/history_watcher.py`

**Step 1: Update check_session_for_project**

```python
async def check_session_for_project(project: ProjectState, bot: Bot, start_poller, start_watcher) -> None:
    """Check if session changed for a project and restart watcher if needed."""
    from .session_manager import project_manager

    if not project.chat_id or not project.cwd:
        return

    old_session = project.session_id
    changed = project_manager.refresh_project_session(project)

    if changed:
        logger.info("session_changed", extra={
            "project": project.project_name,
            "old_session": old_session[:8] if old_session else None,
            "new_session": project.session_id[:8] if project.session_id else None,
        })

        # Cancel old watcher FIRST
        if project.watcher_task:
            project.watcher_task.cancel()
            project.watcher_task = None

        # Start new tasks with send_missed=True
        await project_manager._maybe_start_tasks(project, start_poller, start_watcher, send_missed=True)
```

**Step 2: Update HistoryWatcher._check_for_changes**

Find the `if changed:` block and update:

```python
if changed:
    logger.info("session_changed", extra={
        "project": project.project_name,
        "old_session": old_session[:8] if old_session else None,
        "new_session": project.session_id[:8] if project.session_id else None,
    })

    # Cancel old watcher and start new one
    if project.watcher_task:
        project.watcher_task.cancel()
        project.watcher_task = None

    await self.project_manager._maybe_start_tasks(
        project, self.start_poller, self.start_watcher, send_missed=True
    )
```

**Step 3: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "feat(history_watcher): pass send_missed=True on session change"
```

---

### Task 5: Обновить start_watcher в main.py и bot.py

**Files:**
- Modify: `src/codogram/main.py`
- Modify: `src/codogram/bot.py`

**Step 1: Update main.py**

```python
async def start_watcher(project: ProjectState, send_missed: bool = False) -> asyncio.Task:
    from .watcher import create_watcher_task
    return await create_watcher_task(bot, project, send_missed)
```

**Step 2: Update bot.py _make_task_starters**

```python
def _make_task_starters(bot):
    """Create task starter functions for poller and watcher."""
    async def start_poller(p: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, p)

    async def start_watcher(p: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, p, send_missed)

    return start_poller, start_watcher
```

**Step 3: Commit**

```bash
git add src/codogram/main.py src/codogram/bot.py
git commit -m "feat: update start_watcher signature in main.py and bot.py"
```

---

### Task 6: Унифицировать текст сообщений в bot.py

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Update _connect_or_launch (lines 224-227)**

Replace:
```python
if project.session_id:
    await message.answer(f"Подключено. Сессия: `{project.session_id[:8]}...`", parse_mode="Markdown")
else:
    await message.answer("Подключено. Ожидание сессии Claude.")
```

With:
```python
await message.answer(
    f"Claude запущен в `{project.tmux_session}`\n"
    f"Подключиться: `tmux attach -t {project.tmux_session}`",
    parse_mode="Markdown",
)
```

**Step 2: Update launch_claude_new (lines 316-320)**

Replace:
```python
await message.answer(
    f"Claude запущен в `{project.tmux_session}`\n"
    f"Подключиться: `tmux attach -t {project.tmux_session}`\n\n"
    f"Ожидание регистрации сессии.",
    parse_mode="Markdown",
)
```

With:
```python
await message.answer(
    f"Claude запущен в `{project.tmux_session}`\n"
    f"Подключиться: `tmux attach -t {project.tmux_session}`",
    parse_mode="Markdown",
)
```

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): унифицировать текст сообщений, убрать 'ожидание регистрации'"
```

---

### Task 7: Добавить таймаут 5 минут в watcher

**Files:**
- Modify: `src/codogram/watcher.py`

**Step 1: Add timeout constant**

```python
SESSION_TIMEOUT = 300  # 5 minutes
```

**Step 2: Update watcher_for_session with timeout logic**

```python
async def watcher_for_session(bot: Bot, project: ProjectState,
                              send_missed: bool = False):
    """Watch jsonl for specific project."""
    if not project.jsonl_path:
        logger.warning(f"Watcher: no jsonl_path for project {project.project_name}")
        return

    path = Path(project.jsonl_path)
    chat_id = project.chat_id

    logger.info(f"Watcher started: watching {path} for chat {chat_id}")

    # Wait for file to appear with timeout
    start_time = asyncio.get_event_loop().time()
    while not path.exists():
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > SESSION_TIMEOUT:
            logger.warning(f"Watcher timeout: {path} not found after {SESSION_TIMEOUT}s")
            try:
                await bot.send_message(
                    chat_id,
                    "⚠️ Сессия не обнаружена. Проверьте что Claude запущен."
                )
            except Exception:
                pass
            return
        await asyncio.sleep(1)

    # Send missed entries if requested
    if send_missed:
        missed = find_missed_entries(path)
        # ... rest unchanged ...
```

**Step 3: Commit**

```bash
git add src/codogram/watcher.py
git commit -m "feat(watcher): add 5 minute timeout for session detection"
```

---

### Task 8: Интеграционный тест

**Step 1: Manual test**

1. Убить текущий бот: `pkill -f codogram`
2. Запустить бот: `./restart.sh`
3. В Telegram: `/restart_session` для проекта
4. `/start` — запустить Claude
5. Отправить сообщение
6. Проверить что ответ Claude приходит (не теряется)

**Step 2: Final commit**

```bash
git add -A
git commit -m "feat(codogram): implement missed responses feature

- Add find_missed_entries to find responses after last user message
- Add send_missed parameter to watcher functions
- Pass send_missed=True on session change
- Add 5 minute timeout for session detection
- Unify status messages, remove 'waiting for registration'"
```

---

Plan complete and saved to `docs/plans/2025-12-26-missed-responses.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
