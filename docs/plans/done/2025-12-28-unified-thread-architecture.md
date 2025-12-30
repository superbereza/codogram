# Unified Thread Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify legacy (project.*) and multi-thread (project.threads[id]) mechanisms into a single threads-based approach where thread_id=None is the "main" thread.

**Architecture:** All session state moves to `ThreadInfo`. `ProjectState.threads[None]` becomes the main thread for Private/Simple/Forum General chats. Legacy fields remain for backward compatibility but are populated from threads[None].

**Tech Stack:** Python 3.11+, aiogram, asyncio

---

## Task 1: Add migration in session_manager._load_projects()

**Files:**
- Modify: `src/codogram/session_manager.py:117-137`

**Step 1: Read and understand current _load_projects**

Run: `cat -n src/codogram/session_manager.py | head -160 | tail -50`

Current code loads threads from config but doesn't migrate legacy session_id/jsonl_path to threads[None].

**Step 2: Add migration logic**

```python
def _load_projects(self) -> None:
    """Load projects from config."""
    saved_projects = self._config.get("projects", {})
    for project_name, data in saved_projects.items():
        project = ProjectState(project_name=project_name)
        if isinstance(data, int):
            # Old format: just chat_id
            project.chat_id = data
        else:
            # New format: dict with chat_id and cwd
            project.chat_id = data.get("chat_id")
            project.cwd = data.get("cwd")

            # Load explicit threads first
            threads_data = data.get("threads", {})
            for tid_str, thread_data in threads_data.items():
                tid = None if tid_str == "null" else int(tid_str)
                project.threads[tid] = ThreadInfo(
                    thread_id=tid,
                    name=thread_data.get("name", "main"),
                    session_id=thread_data.get("session_id"),
                    jsonl_path=thread_data.get("jsonl_path"),
                )

            # Migrate legacy → threads[None] if not already present
            if None not in project.threads and data.get("cwd"):
                project.threads[None] = ThreadInfo(
                    thread_id=None,
                    name="main",
                    session_id=data.get("session_id"),
                    jsonl_path=data.get("jsonl_path"),
                )

        self.projects[project_name] = project
```

**Step 3: Verify migration works**

Run: `python -c "from src.codogram.session_manager import ProjectManager; pm = ProjectManager(); print(pm.projects)"`

**Step 4: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(session_manager): migrate legacy fields to threads[None] on load"
```

---

## Task 2: Update session_manager._save() for backward compatibility

**Files:**
- Modify: `src/codogram/session_manager.py:139-155`

**Step 1: Update _save to write threads[None] to legacy fields**

```python
def _save(self) -> None:
    """Persist to disk."""
    projects_data = {}
    for name, p in self.projects.items():
        if p.chat_id is None:
            continue
        project_data = {"chat_id": p.chat_id, "cwd": p.cwd}

        # Backward compat: duplicate threads[None] to legacy fields
        if None in p.threads:
            main_thread = p.threads[None]
            project_data["session_id"] = main_thread.session_id
            project_data["jsonl_path"] = main_thread.jsonl_path

        # Save all threads with full state
        if p.threads:
            project_data["threads"] = {
                str(tid) if tid is not None else "null": {
                    "name": t.name,
                    "session_id": t.session_id,
                    "jsonl_path": t.jsonl_path,
                }
                for tid, t in p.threads.items()
            }
        projects_data[name] = project_data
    self._config["projects"] = projects_data
    self._config.pop("sessions", None)
    save_config(self._config)
```

**Step 2: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(session_manager): save threads[None] to legacy fields for backward compat"
```

---

## Task 3: Update should_cleanup_project() to check threads

**Files:**
- Modify: `src/codogram/session_manager.py:13-50`

**Step 1: Update should_cleanup_project**

```python
def should_cleanup_project(project: 'ProjectState') -> bool:
    """Check if project should be cleaned up (inactive > 30 days).

    Uses jsonl file mtime, not last_activity tracking.
    Does NOT cleanup if tmux session is still running (new project not yet registered).
    """
    import subprocess

    # Check any thread awaiting new session
    for thread in project.threads.values():
        if thread.awaiting_new_session:
            return False
        if thread.binding_task and not thread.binding_task.done():
            return False

    # Legacy checks (for transition period)
    if project.awaiting_new_session:
        return False
    if project.binding_task and not project.binding_task.done():
        return False

    # Check tmux for all threads
    for thread in project.threads.values():
        tmux_name = thread.get_tmux_session(project.project_name)
        result = subprocess.run(
            ["tmux", "has-session", "-t", tmux_name],
            capture_output=True
        )
        if result.returncode == 0:
            return False  # Tmux exists, don't cleanup

    # Legacy tmux check
    if project.tmux_session:
        result = subprocess.run(
            ["tmux", "has-session", "-t", project.tmux_session],
            capture_output=True
        )
        if result.returncode == 0:
            return False

    # Check jsonl mtime for any thread
    newest_mtime = 0
    for thread in project.threads.values():
        if thread.jsonl_path:
            jsonl_path = Path(thread.jsonl_path)
            if jsonl_path.exists():
                try:
                    mtime = jsonl_path.stat().st_mtime
                    newest_mtime = max(newest_mtime, mtime)
                except Exception:
                    pass

    # Legacy jsonl check
    if project.jsonl_path:
        jsonl_path = Path(project.jsonl_path)
        if jsonl_path.exists():
            try:
                mtime = jsonl_path.stat().st_mtime
                newest_mtime = max(newest_mtime, mtime)
            except Exception:
                pass

    if newest_mtime == 0:
        return True  # No jsonl anywhere = cleanup

    age_days = (time.time() - newest_mtime) / 86400
    return age_days > 30
```

**Step 2: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(session_manager): check all threads in should_cleanup_project"
```

---

## Task 4: Unify on_message in bot.py - always use threads

**Files:**
- Modify: `src/codogram/bot.py:1114-1274`

**Step 1: Refactor on_message to always use threads**

Replace the message routing section (after conversation flow handling) with:

```python
    # Normal message - route through threads (unified path)
    project = project_manager.get_by_chat(chat_id)
    if not project:
        return

    # Get or create thread for this topic
    thread = project.threads.get(thread_id)
    logger.debug(f"Message routing: project={project.project_name} thread_id={thread_id} thread={thread}")

    if thread_id is not None and not thread:
        # Unknown topic - create pending ThreadInfo, show hint once
        thread = ThreadInfo(thread_id=thread_id, name="pending")
        project.threads[thread_id] = thread
        project_manager._save()
        await message.answer("Используй /start или /session_new для подключения Claude к этому топику")
        return

    # For thread_id=None (General/Private/Simple), auto-create "main" thread if missing
    if thread_id is None and not thread:
        thread = project.get_or_create_thread(None, "main")
        project_manager._save()

    # Skip pending threads (no tmux yet)
    if thread and thread.name == "pending":
        return

    # All messages now go through thread path
    start_poller, start_watcher = _make_task_starters(message.bot)

    if thread.session_id is None:
        # No session bound - use session binding (match by user message)
        from .history_watcher import poll_for_session_thread

        thread.last_sent_message = message.text

        # Start binding task if not already running
        if not thread.binding_task or thread.binding_task.done():
            logger.debug(f"Starting binding task for thread {thread.name}")
            thread.binding_task = asyncio.create_task(
                poll_for_session_thread(project, thread, message.bot, start_poller, start_watcher)
            )
        else:
            logger.debug(f"Binding task already running for thread {thread.name}")
    else:
        # Session already bound - check if it changed (user might have done /new in tmux)
        from .history_watcher import check_session_for_thread
        await check_session_for_thread(project, thread, message.bot, start_poller, start_watcher)

    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    logger.debug(f"tmux_send: project={project.project_name} tmux={tmux_name}")

    if tmux.exists():
        tmux.send(message.text)
        logger.debug(f"sent_to_tmux: {message.text[:50]}")
    else:
        # No active session - only respond in group chats
        logger.warning(f"no_tmux_session: project={project.project_name}")
        if message.chat.id < 0:  # Negative IDs are groups/channels
            await message.answer("Нет активной сессии Claude. Используй /start для запуска.")
```

**Step 2: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): unify on_message to always use threads"
```

---

## Task 5: Update get_session_for_chat to use threads[None]

**Files:**
- Modify: `src/codogram/bot.py:87-92`

**Step 1: Update get_session_for_chat**

```python
def get_session_for_chat(chat_id: int) -> TmuxSession | None:
    """Get TmuxSession for chat_id (main thread)."""
    project = project_manager.get_by_chat(chat_id)
    if not project:
        return None

    # Try threads[None] first (unified path)
    thread = project.threads.get(None)
    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        return TmuxSession(tmux_name, project.cwd or "/tmp")

    # Legacy fallback
    if project.tmux_session:
        return TmuxSession(project.tmux_session, project.cwd or "/tmp")

    return None
```

**Step 2: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): get_session_for_chat uses threads[None]"
```

---

## Task 6: Update HistoryWatcher._check_for_changes() to iterate threads

**Files:**
- Modify: `src/codogram/history_watcher.py:54-158`

**Step 1: Refactor _check_for_changes to handle all threads**

```python
async def _check_for_changes(self):
    """Check tmux health and session changes for all projects."""
    from .session_manager import should_cleanup_project

    for project in list(self.project_manager.projects.values()):
        if not project.chat_id or not project.cwd:
            continue

        # 1. Check if should cleanup (inactive > 30 days)
        if should_cleanup_project(project):
            logger.info("project_cleanup", extra={"project": project.project_name, "reason": "inactive_30_days"})
            # Cancel all thread tasks
            for thread in project.threads.values():
                if thread.watcher_task:
                    thread.watcher_task.cancel()
                if thread.poller_task:
                    thread.poller_task.cancel()
            # Cancel legacy tasks
            if project.watcher_task:
                project.watcher_task.cancel()
            if project.poller_task:
                project.poller_task.cancel()
            del self.project_manager.projects[project.project_name]
            continue

        # 2. Check thread health (tmux died detection for ALL threads)
        for thread in list(project.threads.values()):
            # Skip if awaiting or binding
            if thread.awaiting_new_session:
                continue
            if thread.binding_task and not thread.binding_task.done():
                continue

            tmux_name = thread.get_tmux_session(project.project_name)
            tmux = TmuxSession(tmux_name, project.cwd)

            # Check if tmux died
            if thread.session_id and not tmux.exists():
                logger.warning(f"thread_tmux_died: project={project.project_name}, thread={thread.name}")

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

        # NOTE: Legacy project-level checks removed - all handled through threads now
```

**Step 2: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "refactor(history_watcher): iterate threads instead of legacy project fields"
```

---

## Task 7: Remove poll_for_session (legacy) from history_watcher.py

**Files:**
- Modify: `src/codogram/history_watcher.py:221-291`

**Step 1: Delete poll_for_session function**

Remove the entire `poll_for_session` function (lines 221-291).

**Step 2: Update imports in bot.py**

Search for `from .history_watcher import poll_for_session` and remove it if present.

**Step 3: Commit**

```bash
git add src/codogram/history_watcher.py src/codogram/bot.py
git commit -m "refactor: remove legacy poll_for_session, use poll_for_session_thread"
```

---

## Task 8: Remove check_session_for_project (legacy) from history_watcher.py

**Files:**
- Modify: `src/codogram/history_watcher.py:160-188`

**Step 1: Delete check_session_for_project function**

Remove the entire function.

**Step 2: Commit**

```bash
git add src/codogram/history_watcher.py
git commit -m "refactor: remove legacy check_session_for_project"
```

---

## Task 9: Remove watcher_for_session (legacy) from watcher.py

**Files:**
- Modify: `src/codogram/watcher.py:239-319`

**Step 1: Delete watcher_for_session and create_watcher_task**

Remove both functions. Keep only `send_entry_to_telegram`, `JsonlWatcher`, and `watch_jsonl`.

**Step 2: Update references**

Search for `create_watcher_task` and `watcher_for_session` in other files. Update session_manager.py if needed.

**Step 3: Commit**

```bash
git add src/codogram/watcher.py src/codogram/session_manager.py
git commit -m "refactor: remove legacy watcher_for_session, use watch_thread_jsonl"
```

---

## Task 10: Update restore_projects in session_manager.py

**Files:**
- Modify: `src/codogram/session_manager.py:240-302`

**Step 1: Update restore_projects to work with threads**

```python
async def restore_projects(self, bot, start_poller, start_watcher) -> None:
    """Restore sessions from history.jsonl after bot restart."""
    from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention
    from .tmux_selector import create_tmux_selection_keyboard
    from .history_watcher import poll_for_session_thread

    for project in list(self.projects.values()):
        if not project.chat_id or not project.cwd:
            continue

        # 1. Check if should cleanup
        if should_cleanup_project(project):
            logger.info("project_cleanup", extra={"project": project.project_name, "reason": "inactive_30_days"})
            self.projects.pop(project.project_name, None)
            continue

        logger.info("project_restored", extra={"project": project.project_name})

        # 2. Ensure threads[None] exists for main thread
        if None not in project.threads:
            project.threads[None] = ThreadInfo(thread_id=None, name="main")

        # 3. For each thread, try to restore tmux and session
        for thread in project.threads.values():
            tmux_name = thread.get_tmux_session(project.project_name)

            # Check if tmux exists
            import subprocess
            result = subprocess.run(
                ["tmux", "has-session", "-t", tmux_name],
                capture_output=True
            )

            if result.returncode != 0:
                # No tmux - will need /start to launch
                continue

            # Tmux exists - refresh session if we have one
            if thread.session_id and thread.jsonl_path:
                from pathlib import Path
                if Path(thread.jsonl_path).exists():
                    # Start watcher for this thread
                    from .history_watcher import watch_thread_jsonl
                    if not thread.watcher_task or thread.watcher_task.done():
                        thread.watcher_task = asyncio.create_task(
                            watch_thread_jsonl(bot, project, thread)
                        )
                    # Start poller for this thread
                    from .permission_poller import create_poller_task_for_thread
                    if not thread.poller_task or thread.poller_task.done():
                        thread.poller_task = await create_poller_task_for_thread(bot, project, thread)

    self._save()
```

**Step 2: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "refactor(session_manager): restore_projects works with threads"
```

---

## Task 11: Update _maybe_start_tasks to work with threads

**Files:**
- Modify: `src/codogram/session_manager.py:227-238`

**Step 1: Deprecate or remove _maybe_start_tasks**

Since threads handle their own tasks, this function becomes obsolete. Either:
- Remove it entirely
- Or keep it as a no-op with deprecation warning

```python
async def _maybe_start_tasks(self, project: ProjectState, start_poller, start_watcher,
                             send_missed: bool = False) -> None:
    """DEPRECATED: Tasks are now started per-thread in poll_for_session_thread."""
    logger.warning("_maybe_start_tasks called but is deprecated - tasks now handled per-thread")
```

**Step 2: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "deprecate: _maybe_start_tasks replaced by per-thread task management"
```

---

## Task 12: Update launch_claude_new to create threads[None]

**Files:**
- Modify: `src/codogram/bot.py:336-448`

**Step 1: Update launch_claude_new**

At the start of the function, ensure threads[None] is created:

```python
async def launch_claude_new(message: Message, project: ProjectState, start_poller, start_watcher):
    """Launch Claude in tmux session using new ProjectState."""
    import subprocess

    # Ensure main thread exists
    thread = project.get_or_create_thread(None, "main")

    convention = f"claude-{project.project_name}"

    # Block session discovery during startup
    thread.awaiting_new_session = True
    # ... rest of function
```

Also update at the end to set thread.session_id once discovered.

**Step 2: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): launch_claude_new uses threads[None]"
```

---

## Task 13: Clean up legacy fields usage

**Files:**
- Modify: `src/codogram/bot.py`
- Modify: `src/codogram/session_manager.py`
- Modify: `src/codogram/history_watcher.py`

**Step 1: Add deprecation comments to legacy fields in ProjectState**

```python
@dataclass
class ProjectState:
    """State for a single project."""
    project_name: str
    chat_id: int | None = None
    cwd: str | None = None

    # Multi-thread support: thread_id -> ThreadInfo
    threads: dict[int | None, ThreadInfo] = field(default_factory=dict)

    # DEPRECATED: Legacy fields kept for backward compatibility with old configs
    # All new code should use threads[None] for main thread
    session_id: str | None = None  # DEPRECATED: use threads[None].session_id
    jsonl_path: str | None = None  # DEPRECATED: use threads[None].jsonl_path
    watcher_task: asyncio.Task | None = field(default=None, repr=False)  # DEPRECATED
    tmux_session: str | None = None  # DEPRECATED: use threads[None].get_tmux_session()
    poller_task: asyncio.Task | None = field(default=None, repr=False)  # DEPRECATED
    last_sent_message: str | None = None  # DEPRECATED
    binding_task: asyncio.Task | None = field(default=None, repr=False)  # DEPRECATED
    awaiting_new_session: bool = False  # DEPRECATED
```

**Step 2: Search and update remaining usages**

Run: `grep -rn "project\.session_id\|project\.jsonl_path\|project\.watcher_task\|project\.tmux_session" src/codogram/`

Update each to use threads[None] instead.

**Step 3: Commit**

```bash
git add src/codogram/
git commit -m "refactor: mark legacy fields as deprecated, update remaining usages"
```

---

## Task 14: Manual testing

**Step 1: Test Private chat**

1. `/start myproject` → should create threads[None]
2. Send message → should route through threads[None]
3. Verify no duplication in responses

**Step 2: Test Simple group**

1. Add bot to non-forum group
2. `/start` → should create threads[None]
3. Messages work correctly

**Step 3: Test Forum group - General only**

1. Add bot to forum group
2. `/start` in General → threads[None]
3. Messages in General work correctly

**Step 4: Test Forum group - General + Topics**

1. `/start` in General → threads[None]
2. `/session_new` → threads[456] with magic name
3. Send message in General → ONLY goes to General (no duplication!)
4. Send message in topic → ONLY goes to topic

**Step 5: Test bot restart**

1. Stop and restart bot
2. Verify sessions are restored correctly
3. Verify no duplication after restart

**Step 6: Commit test results**

```bash
git commit --allow-empty -m "test: manual testing passed for unified thread architecture"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Migration in _load_projects | session_manager.py |
| 2 | Backward compat in _save | session_manager.py |
| 3 | should_cleanup_project checks threads | session_manager.py |
| 4 | Unify on_message | bot.py |
| 5 | get_session_for_chat uses threads[None] | bot.py |
| 6 | HistoryWatcher iterates threads | history_watcher.py |
| 7 | Remove poll_for_session | history_watcher.py |
| 8 | Remove check_session_for_project | history_watcher.py |
| 9 | Remove watcher_for_session | watcher.py |
| 10 | Update restore_projects | session_manager.py |
| 11 | Deprecate _maybe_start_tasks | session_manager.py |
| 12 | launch_claude_new uses threads[None] | bot.py |
| 13 | Clean up legacy fields | all |
| 14 | Manual testing | - |
