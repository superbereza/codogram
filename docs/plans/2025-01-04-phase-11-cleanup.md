# Phase 11: Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate tech debt: unify permission_poller (2→1 function), delete dead code, move constants to config.

**Architecture:** Refactor permission_poller to single function with `thread: ThreadInfo | None` parameter. Delete unused functions. Centralize timing constants in Settings.

**Tech Stack:** Python, aiogram, pydantic-settings, pytest

---

## Task 1: Add timing constants to config.py

**Files:**
- Modify: `src/codogram/config.py:6-18`
- Test: `tests/test_config.py` (create)

**Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
# tests/test_config.py
"""Tests for config module."""
import pytest
from codogram.config import Settings


def test_settings_has_timing_constants():
    """Settings should have timing constants with defaults."""
    # Create settings with minimal required fields
    s = Settings(
        telegram_token="test",
        admin_ids="123",
        base_dir="/tmp"
    )

    # Timing constants with expected defaults
    assert s.permission_poller_debounce == 0.5
    assert s.permission_poller_interval == 0.5
    assert s.history_watcher_interval == 15
    assert s.session_binding_timeout == 300
    assert s.session_binding_interval == 0.5
    assert s.jsonl_watcher_interval == 0.5
    assert s.claude_launch_timeout == 120
    assert s.project_cleanup_days == 30
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_config.py -v`
Expected: FAIL with "AttributeError: 'Settings' object has no attribute 'permission_poller_debounce'"

**Step 3: Write minimal implementation**

Update `src/codogram/config.py`:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    telegram_token: str
    admin_ids: str  # Comma-separated list of admin user IDs
    base_dir: str  # e.g. /home/user/dev
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # Timing constants (seconds)
    permission_poller_debounce: float = 0.5
    permission_poller_interval: float = 0.5
    history_watcher_interval: int = 15
    session_binding_timeout: int = 300
    session_binding_interval: float = 0.5
    jsonl_watcher_interval: float = 0.5
    claude_launch_timeout: int = 120
    project_cleanup_days: int = 30

    def get_admin_ids(self) -> set[int]:
        """Parse admin_ids string into set of ints."""
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_config.py -v`
Expected: PASS

**Step 5: Run all tests**

Run: `PYTHONPATH=src pytest tests/ -q --tb=short`
Expected: All 230+ tests pass

**Step 6: Commit**

```bash
git add src/codogram/config.py tests/test_config.py
git commit -m "feat(config): add timing constants to Settings"
```

---

## Task 2: Delete find_missed_entries dead code

**Files:**
- Modify: `src/codogram/watcher.py:28-50`

**Step 1: Verify function is not used**

Run: `grep -r "find_missed_entries" src/codogram/ --include="*.py" | grep -v "^src/codogram/watcher.py:.*def find_missed_entries"`
Expected: No output (function not called anywhere)

**Step 2: Delete the function**

Remove lines 28-50 from `src/codogram/watcher.py`:

```python
# DELETE THIS ENTIRE FUNCTION:
def find_missed_entries(path: Path) -> list[ParsedEntry]:
    """Find entries that might have been missed during downtime.

    Returns entries from the last hour that haven't been processed.
    This is useful when the bot restarts and needs to catch up.
    """
    try:
        entries = list(parse_history(path))
        if not entries:
            return []

        # Get entries from the last hour
        cutoff = datetime.now() - timedelta(hours=1)
        recent = [e for e in entries if e.timestamp > cutoff]

        return recent
    except Exception as e:
        logger.warning(f"find_missed_entries error: {e}")
        return []
```

**Step 3: Run tests**

Run: `PYTHONPATH=src pytest tests/ -q --tb=short`
Expected: All tests pass (function was never used)

**Step 4: Commit**

```bash
git add src/codogram/watcher.py
git commit -m "refactor(watcher): remove unused find_missed_entries"
```

---

## Task 3: Delete _maybe_start_tasks deprecated code

**Files:**
- Modify: `src/codogram/session_manager.py:319, 323-326`

**Step 1: Find the call site**

The call is on line 319:
```python
await self._maybe_start_tasks(project, start_poller, start_watcher)
```

**Step 2: Delete the call (line 319)**

Remove this line from `restore_projects` method.

**Step 3: Delete the method (lines 323-326)**

Remove:
```python
async def _maybe_start_tasks(self, project: ProjectState, start_poller, start_watcher,
                             telegram_queue=None):
    """DEPRECATED: Tasks are now started per-thread in restore_thread_tasks."""
    logger.warning("_maybe_start_tasks called but is deprecated - tasks now handled per-thread")
```

**Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/ -q --tb=short`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "refactor(session_manager): remove deprecated _maybe_start_tasks"
```

---

## Task 4: Create unified permission_poller function

**Files:**
- Modify: `src/codogram/permission_poller.py`
- Test: `tests/test_permission_poller.py`

**Step 1: Write test for unified function signature**

Add to `tests/test_permission_poller.py`:

```python
# tests/test_permission_poller.py
import inspect
from codogram.permission_poller import (
    PollerState,
    permission_poller,
    create_poller_task,
    create_poller_task_for_thread,
)


def test_poller_state_enum():
    assert PollerState.IDLE.value == "idle"
    assert PollerState.DEBOUNCING.value == "debouncing"
    assert PollerState.SHOWING.value == "showing"


def test_permission_poller_signature():
    """Unified permission_poller accepts optional thread parameter."""
    sig = inspect.signature(permission_poller)
    params = list(sig.parameters.keys())

    assert "bot" in params
    assert "project" in params
    assert "telegram_queue" in params
    assert "thread" in params

    # thread should have default None
    thread_param = sig.parameters["thread"]
    assert thread_param.default is None


def test_create_poller_task_exists():
    """create_poller_task should exist for project-level polling."""
    assert callable(create_poller_task)


def test_create_poller_task_for_thread_exists():
    """create_poller_task_for_thread should exist for thread-level polling."""
    assert callable(create_poller_task_for_thread)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_permission_poller.py -v`
Expected: FAIL with "cannot import name 'permission_poller'"

**Step 3: Implement unified permission_poller**

Replace the two functions with one unified function in `src/codogram/permission_poller.py`:

```python
async def permission_poller(
    bot: Bot,
    project: ProjectState,
    telegram_queue: "TelegramQueue",
    thread: ThreadInfo | None = None,
) -> None:
    """
    Unified background poller for permission prompts.

    Args:
        bot: Telegram bot instance
        project: Project state
        telegram_queue: Queue for sending messages
        thread: Thread info for topic-level polling, None for project-level

    Polls tmux every 0.5s, uses debounce before sending.
    State machine: IDLE → DEBOUNCING → SHOWING → IDLE
    """
    from .config import settings

    # Determine context based on thread presence
    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        thread_id = thread.thread_id
        auto_accept_flag = thread.auto_accept
        log_prefix = f"Thread poller [{thread.name}]"
        context_name = thread.name
    else:
        tmux_name = project.tmux_session
        thread_id = None
        auto_accept_flag = project.auto_accept
        log_prefix = "Poller"
        context_name = project.project_name

    logger.info(f"{log_prefix} started for {context_name} (tmux: {tmux_name})")

    tmux = TmuxSession(tmux_name, project.cwd)
    chat_id = project.chat_id

    state = PollerState.IDLE
    debounce_start = 0.0
    last_options = None
    last_body = None
    content_msg_ids: list[int] = []
    kb_msg_id: int | None = None

    DEBOUNCE_TIME = settings.permission_poller_debounce
    POLL_INTERVAL = settings.permission_poller_interval

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            screen = tmux.capture_pane()
            parsed = parse_screen(screen)
        except Exception as e:
            logger.warning(f"{log_prefix}: capture error: {e}")
            continue

        # Crash detection
        crash_reason = _detect_crash(screen)
        if crash_reason:
            logger.error(f"{log_prefix}: Claude crashed! Reason: {crash_reason}")
            try:
                batch = OutgoingBatch(
                    chat_id=chat_id,
                    thread_id=thread_id,
                    messages=[{"text": f"`[!]` Claude crashed: {crash_reason}\nUse /restart to restart.", "parse_mode": "MarkdownV2"}],
                )
                await telegram_queue.enqueue_nowait(batch)
            except Exception:
                pass
            return  # Exit poller

        is_permission = isinstance(parsed, PermissionPrompt)

        # Debug logging (only for project-level)
        if not thread and "❯" in screen and not is_permission:
            logger.debug(f"{log_prefix}: ❯ found but no permission! parsed={type(parsed).__name__}")

        # State machine transitions
        if state == PollerState.IDLE:
            if is_permission:
                logger.debug(f"{log_prefix} IDLE→DEBOUNCING: detected permission, options={parsed.options}")
                if not thread:
                    logger.debug(f"{log_prefix}: body={parsed.body[:100] if parsed.body else 'none'}...")
                state = PollerState.DEBOUNCING
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options

        elif state == PollerState.DEBOUNCING:
            if not is_permission:
                logger.debug(f"{log_prefix} DEBOUNCING→IDLE: permission disappeared")
                state = PollerState.IDLE
                last_options = None
            elif parsed.options != last_options:
                debounce_start = asyncio.get_event_loop().time()
                last_options = parsed.options
            else:
                elapsed = asyncio.get_event_loop().time() - debounce_start
                if elapsed >= DEBOUNCE_TIME:
                    # Check auto-accept
                    if auto_accept_flag:
                        if await try_auto_accept(
                            parsed.options, parsed.body, tmux,
                            telegram_queue, chat_id, thread_id, context_name
                        ):
                            state = PollerState.IDLE
                            last_options = None
                            continue

                    logger.debug(f"{log_prefix} DEBOUNCING→SHOWING: sending to Telegram")
                    if not thread:
                        logger.debug(f"{log_prefix}: body preview: {parsed.body[:200]}...")
                    try:
                        # Build batch of body messages
                        body_messages = []
                        if parsed.body:
                            body_text = SEPARATOR_SOLID + "\n" + parsed.body
                            body_messages.append({"text": body_text, "parse_mode": "MarkdownV2"})

                        # Options as text
                        options_text = "\n".join(parsed.options)
                        body_messages.append({"text": options_text})

                        # Send body through queue, get IDs for cleanup
                        batch = OutgoingBatch(
                            chat_id=chat_id,
                            thread_id=thread_id,
                            messages=body_messages,
                        )
                        content_msg_ids = await telegram_queue.enqueue(batch)

                        # Keyboard through queue (rate limited)
                        kb = permission_keyboard(parsed.options, tmux_name)
                        kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
                            chat_id=chat_id,
                            text="👆",
                            reply_markup=kb,
                            thread_id=thread_id,
                        ))
                        kb_msg_id = kb_msg_ids[0] if kb_msg_ids else None
                        if kb_msg_id:
                            permission_messages[kb_msg_id] = content_msg_ids

                        state = PollerState.SHOWING
                        last_body = parsed.body
                        logger.debug(f"{log_prefix} SHOWING: sent {len(parsed.options)} options, kb_msg={kb_msg_id}")
                    except Exception as e:
                        logger.warning(f"{log_prefix}: send error: {e}")
                        state = PollerState.IDLE

        elif state == PollerState.SHOWING:
            if not is_permission:
                logger.debug(f"{log_prefix} SHOWING→IDLE: permission gone, cleaning up")
                if kb_msg_id and kb_msg_id in permission_messages:
                    for msg_id in permission_messages[kb_msg_id]:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                    try:
                        await bot.delete_message(chat_id, kb_msg_id)
                    except Exception:
                        pass
                    permission_messages.pop(kb_msg_id, None)

                state = PollerState.IDLE
                last_options = None
                last_body = None
                content_msg_ids = []
                kb_msg_id = None
            elif parsed.options != last_options or parsed.body != last_body:
                logger.debug(f"{log_prefix} SHOWING: body/options changed, resending")
                try:
                    # Delete old messages
                    if kb_msg_id and kb_msg_id in permission_messages:
                        for msg_id in permission_messages[kb_msg_id]:
                            try:
                                await bot.delete_message(chat_id, msg_id)
                            except Exception:
                                pass
                        try:
                            await bot.delete_message(chat_id, kb_msg_id)
                        except Exception:
                            pass
                        permission_messages.pop(kb_msg_id, None)

                    # Build new body messages
                    body_messages = []
                    if parsed.body:
                        body_text = SEPARATOR_SOLID + "\n" + parsed.body
                        body_messages.append({"text": body_text, "parse_mode": "MarkdownV2"})

                    options_text = "\n".join(parsed.options)
                    body_messages.append({"text": options_text})

                    # Send through queue
                    batch = OutgoingBatch(chat_id=chat_id, thread_id=thread_id, messages=body_messages)
                    content_msg_ids = await telegram_queue.enqueue(batch)

                    # Keyboard through queue (rate limited)
                    kb = permission_keyboard(parsed.options, tmux_name)
                    kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
                        chat_id=chat_id,
                        text="👆",
                        reply_markup=kb,
                        thread_id=thread_id,
                    ))
                    kb_msg_id = kb_msg_ids[0] if kb_msg_ids else None
                    if kb_msg_id:
                        permission_messages[kb_msg_id] = content_msg_ids

                    last_options = parsed.options
                    last_body = parsed.body
                except Exception as e:
                    logger.warning(f"{log_prefix}: resend error: {e}")


async def create_poller_task(bot: Bot, project: ProjectState, telegram_queue: "TelegramQueue") -> asyncio.Task:
    """Create permission poller task for project (no thread)."""
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=None))


async def create_poller_task_for_thread(bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue") -> asyncio.Task:
    """Create permission poller task for a specific thread."""
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=thread))
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_permission_poller.py -v`
Expected: PASS

**Step 5: Run all tests**

Run: `PYTHONPATH=src pytest tests/ -q --tb=short`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/codogram/permission_poller.py tests/test_permission_poller.py
git commit -m "refactor(permission_poller): unify into single function with thread param"
```

---

## Task 5: Update hardcoded constants to use settings

**Files:**
- Modify: `src/codogram/history_watcher.py`
- Modify: `src/codogram/watcher.py`
- Modify: `src/codogram/launch_animation.py`
- Modify: `src/codogram/session_manager.py`

**Step 1: Update history_watcher.py**

Replace hardcoded values:
- Line 16: `REFRESH_INTERVAL = 15` → `from .config import settings` + use `settings.history_watcher_interval`
- Line 238: `BINDING_TIMEOUT = 300` → `settings.session_binding_timeout`
- Line 239: `BINDING_INTERVAL = 0.5` → `settings.session_binding_interval`

**Step 2: Update watcher.py**

Replace:
- Lines 139, 172: `poll_interval = 0.5` → `settings.jsonl_watcher_interval`

**Step 3: Update launch_animation.py**

Replace:
- Line 104: `120` (implicit timeout) → `settings.claude_launch_timeout`

**Step 4: Update session_manager.py**

Replace:
- Line 79: `30` (cleanup days) → `settings.project_cleanup_days`

**Step 5: Run tests**

Run: `PYTHONPATH=src pytest tests/ -q --tb=short`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/codogram/history_watcher.py src/codogram/watcher.py \
        src/codogram/launch_animation.py src/codogram/session_manager.py
git commit -m "refactor: use settings for timing constants instead of hardcoded values"
```

---

## Definition of Done

- [ ] Timing constants added to config.py with tests
- [ ] find_missed_entries deleted
- [ ] _maybe_start_tasks deleted
- [ ] permission_poller unified (1 function instead of 2)
- [ ] Hardcoded constants replaced with settings.*
- [ ] All 230+ tests pass
- [ ] LOC reduction: ~170 lines

---

## Metrics

| File | Before | After | Saved |
|------|--------|-------|-------|
| permission_poller.py | 452 LOC | ~280 LOC | ~170 |
| watcher.py | - | - | 23 |
| session_manager.py | - | - | 8 |
| **Total** | - | - | **~200** |
