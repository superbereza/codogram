# Session Binder (Telegram Commands) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix thread session mixup bug by adding `/new` and `/clear` Telegram commands that properly track which thread awaits a new session.

**Architecture:** When user sends `/new` or `/clear` in Telegram, bot marks thread as `awaiting_new_session=true`, sends command to tmux, and HistoryWatcher binds new session to the awaiting thread.

**Tech Stack:** Python 3.11+, aiogram (Telegram), pytest

**Design:** [docs/designs/2025-12-29-session-binder-design.md](../designs/2025-12-29-session-binder-design.md)

---

## Task 1: ~~Add awaiting_new_session field to ThreadInfo~~ SKIP

> **Already implemented.** Field `awaiting_new_session: bool = False` exists in `ThreadInfo` at `session_manager.py:99`.

---

## Task 1b: Persist awaiting_new_session in config

**Files:**
- Modify: `src/codogram/session_manager.py`

**Why:** If bot restarts while thread is awaiting new session, the flag is lost and thread becomes stuck.

**Step 1: Update _save() to include awaiting_new_session**

Find the thread serialization in `_save()` method and add the field:

```python
if p.threads:
    project_data["threads"] = {
        str(tid) if tid is not None else "null": {
            "name": t.name,
            "session_id": t.session_id,
            "jsonl_path": t.jsonl_path,
            "awaiting_new_session": t.awaiting_new_session,  # ADD THIS
        }
        for tid, t in p.threads.items()
    }
```

**Step 2: Update _load_projects() to read awaiting_new_session**

Find where ThreadInfo is created in `_load_projects()` and add:

```python
project.threads[tid] = ThreadInfo(
    thread_id=tid,
    name=thread_data.get("name", "main"),
    session_id=thread_data.get("session_id"),
    jsonl_path=thread_data.get("jsonl_path"),
    awaiting_new_session=thread_data.get("awaiting_new_session", False),  # ADD THIS
)
```

**Step 3: Verify syntax**

Run: `python -m py_compile src/codogram/session_manager.py && echo "OK"`
Expected: OK

**Step 4: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "fix(session_manager): persist awaiting_new_session flag"
```

---

## Task 2: Add /new command handler

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Add import for Command at top of file (if not present)**

Check if `Command` is imported from aiogram.filters. If not, add it.

**Step 2: Add /new command handler**

Add after other command handlers (around line 200):

```python
@router.message(Command("new"))
async def cmd_new(message: Message):
    """Start new Claude session in current thread."""
    if not is_admin(message.from_user.id):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Проект не зарегистрирован. Используй /start")
        return

    thread_id = message.message_thread_id
    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("Thread не найден. Используй /start")
        return

    tmux_name = thread.get_tmux_session(project.project_name)

    if not is_tmux_session_exists(tmux_name):
        await message.answer("tmux сессия не найдена. Запусти Claude в терминале.")
        return

    # NOTE: Do NOT cancel watcher here - let it continue watching old session.
    # _bind_thread_to_session will cancel it when new session is found.
    # This prevents thread becoming "dead" if user cancels /new in Claude.

    # Mark thread as awaiting new session
    thread.awaiting_new_session = True
    thread.last_sent_message = None
    project_manager._save()

    # Send /new to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_keys("/new")

    await message.answer("⏳ Создаю новую сессию...")
```

**Step 3: Verify syntax**

Run: `python -m py_compile src/codogram/bot.py && echo "OK"`
Expected: OK

**Step 4: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): add /new command to start fresh Claude session"
```

---

## Task 3: Add /clear command handler

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Add /clear command handler**

Add right after /new handler:

```python
@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Clear Claude session and start fresh."""
    if not is_admin(message.from_user.id):
        return

    project = project_manager.get_by_chat(message.chat.id)
    if not project:
        await message.answer("Проект не зарегистрирован. Используй /start")
        return

    thread_id = message.message_thread_id
    thread = project.threads.get(thread_id)
    if not thread:
        await message.answer("Thread не найден. Используй /start")
        return

    tmux_name = thread.get_tmux_session(project.project_name)

    if not is_tmux_session_exists(tmux_name):
        await message.answer("tmux сессия не найдена. Запусти Claude в терминале.")
        return

    # NOTE: Do NOT cancel watcher here - same reason as cmd_new

    # Mark thread as awaiting new session
    thread.awaiting_new_session = True
    thread.last_sent_message = None
    project_manager._save()

    # Send /clear to tmux
    tmux = TmuxSession(tmux_name, project.cwd)
    tmux.send_keys("/clear")

    await message.answer("⏳ Очищаю сессию...")
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/bot.py && echo "OK"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): add /clear command to clear Claude session"
```

---

## Task 4: Add _bind_awaiting_threads to HistoryWatcher

**Files:**
- Modify: `src/codogram/history_watcher.py`

**Step 1: Add _bind_awaiting_threads method**

Add to `HistoryWatcher` class after `_check_for_changes`:

```python
async def _bind_awaiting_threads(self, project: ProjectState):
    """Find new sessions and bind to awaiting threads.

    NOTE: Binds only ONE thread per cycle to prevent race condition where
    multiple awaiting threads bind to the same session.
    """
    from .history_reader import find_session_for_project

    # Get latest session once
    new_session = find_session_for_project(project.cwd)
    if not new_session:
        return

    # Find first awaiting thread that can bind to this session
    for thread in project.threads.values():
        if not thread.awaiting_new_session:
            continue
        if thread.session_id == new_session:
            continue  # Already has this session

        # Bind ONE thread and exit - next cycle will handle others
        await self._bind_thread_to_session(project, thread, new_session)
        return


async def _bind_thread_to_session(
    self,
    project: ProjectState,
    thread: ThreadInfo,
    new_session_id: str
):
    """Bind thread to new session."""
    from .history_reader import compute_jsonl_path

    logger.info(
        f"session_bound: project={project.project_name}, thread={thread.name}, "
        f"old={thread.session_id[:8] if thread.session_id else None}, "
        f"new={new_session_id[:8]}"
    )

    # Cancel old watcher if exists
    if thread.watcher_task:
        thread.watcher_task.cancel()
        thread.watcher_task = None

    # Update binding
    thread.session_id = new_session_id
    thread.jsonl_path = str(compute_jsonl_path(project.cwd, new_session_id))
    thread.awaiting_new_session = False

    # Start new watcher
    thread.watcher_task = asyncio.create_task(
        watch_thread_jsonl(self.bot, project, thread, self.telegram_queue)
    )

    # Restart permission poller
    if thread.poller_task:
        thread.poller_task.cancel()
    from .permission_poller import create_poller_task_for_thread
    thread.poller_task = await create_poller_task_for_thread(
        self.bot, project, thread, self.telegram_queue
    )

    # Notify user
    from .telegram_queue import OutgoingBatch
    try:
        batch = OutgoingBatch(
            chat_id=project.chat_id,
            thread_id=thread.thread_id,
            messages=[{"text": "✅ Новая сессия создана"}],
        )
        # enqueue_nowait is sync, no await needed
        self.telegram_queue.enqueue_nowait(batch)
    except Exception:
        pass

    # Save config
    self.project_manager._save()
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/history_watcher.py && echo "OK"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "feat(history_watcher): add _bind_awaiting_threads for session rebinding"
```

---

## Task 5: Call _bind_awaiting_threads in _check_for_changes

**Files:**
- Modify: `src/codogram/history_watcher.py`

**Step 1: Add call to _bind_awaiting_threads**

In `_check_for_changes` method, after the thread health checks loop, add:

```python
            # After thread health checks, bind awaiting threads
            await self._bind_awaiting_threads(project)
```

Find the end of the for loop that checks thread health (after `thread.jsonl_path = None`) and add the call there.

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/history_watcher.py && echo "OK"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "feat(history_watcher): call _bind_awaiting_threads in check loop"
```

---

## Task 6: Register new commands in main.py

**Files:**
- Modify: `src/codogram/main.py`

**Step 1: Update bot commands list**

Find `set_my_commands` call and add `/new` and `/clear`:

```python
await bot.set_my_commands([
    BotCommand(command="start", description="Start Claude / show status"),
    BotCommand(command="new", description="Start new Claude session"),
    BotCommand(command="clear", description="Clear and start fresh session"),
    BotCommand(command="session_new", description="Create new Claude thread"),
    BotCommand(command="session_close", description="Close Claude thread (use in topic)"),
    BotCommand(command="restart_session", description="Restart Claude session"),
    BotCommand(command="my_chat_id", description="Show your user ID"),
    BotCommand(command="esc", description="Send Escape to Claude"),
])
```

**Step 2: Verify syntax**

Run: `python -m py_compile src/codogram/main.py && echo "OK"`
Expected: OK

**Step 3: Commit**

```bash
git add src/codogram/main.py
git commit -m "feat(main): register /new and /clear commands"
```

---

## Task 7: Remove dead code check_session_for_thread

**Files:**
- Modify: `src/codogram/history_watcher.py`
- Modify: `tests/test_history_watcher.py`

**Step 1: Remove check_session_for_thread function**

Delete `check_session_for_thread` function from `history_watcher.py` (approximately lines 238-265).

**Step 2: Remove unused import in bot.py (if exists)**

Check if `check_session_for_thread` is imported in `bot.py`. If so, remove the import.

**Step 3: Update tests**

In `tests/test_history_watcher.py`, remove or update any tests for `check_session_for_thread`.

**Step 4: Verify syntax**

Run: `python -m py_compile src/codogram/history_watcher.py && python -m py_compile src/codogram/bot.py && echo "OK"`
Expected: OK

**Step 5: Run tests**

Run: `pytest tests/test_history_watcher.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/codogram/history_watcher.py src/codogram/bot.py tests/test_history_watcher.py
git commit -m "refactor(history_watcher): remove unused check_session_for_thread"
```

---

## Task 8: Manual testing

**Step 1: Restart bot**

Run: `./restart.sh`
Expected: Bot restarted

**Step 2: Test /new command**

1. Go to Telegram topic with active Claude session
2. Send `/new`
3. Expected:
   - Bot shows "⏳ Создаю новую сессию..."
   - Claude creates new session
   - Bot shows "✅ Новая сессия создана"
   - Messages from Claude continue to arrive

**Step 3: Test /clear command**

1. Send `/clear` in same topic
2. Expected:
   - Bot shows "⏳ Очищаю сессию..."
   - Claude clears and starts new session
   - Bot shows "✅ Новая сессия создана"

**Step 4: Test session mixup fix**

1. Have two topics with different Claude sessions
2. Do `/new` in one topic
3. Verify other topic still receives its Claude messages (no mixup)

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat: session binder with /new and /clear commands

- Add /new command to start fresh Claude session
- Add /clear command to clear and restart session
- Add awaiting_new_session flag to ThreadInfo
- HistoryWatcher binds new sessions to awaiting threads
- Fixes: thread session mixup bug

See: docs/designs/2025-12-29-session-binder-design.md"
```

---

## Summary

**Total tasks:** 9 (Task 1 skipped - already implemented)
**Key changes:**
1. ~~`session_manager.py` - `awaiting_new_session` field~~ (already exists)
1b. `session_manager.py` - persist `awaiting_new_session` in `_save/_load`
2. `bot.py` - `/new` and `/clear` command handlers
3. `history_watcher.py` - `_bind_awaiting_threads` method + remove dead code
4. `main.py` - register new commands

**Testing:**
- Manual testing of /new and /clear
- Verify session mixup bug is fixed

**Known Limitations:**
- 15-sec binding delay: Tool calls during `/new` → session bound may be delayed (HistoryWatcher polls every 15 sec). No data loss, just latency.
- If user cancels /new in Claude terminal, thread continues with old session (graceful degradation).
