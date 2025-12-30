# Background Launch Animation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Non-blocking Claude launch with animated status messages.

**Architecture:** Background task for launch, text statuses, face animation if waiting > 3 sec, all edits through TelegramQueue.

**Tech Stack:** Python 3.11+, asyncio, aiogram 3.x, pytest

**Design:** [docs/designs/2025-12-29-background-launch-animation.md](../designs/2025-12-29-background-launch-animation.md)

**Pre-existing infrastructure:**
- `poll_for_session_thread` — exists in `history_watcher.py:244`
- `create_poller_task_for_thread` — exists in `permission_poller.py:193`
- `_make_task_starters` — exists in `bot.py:161`
- `telegram_queue.enqueue()` — already returns `list[int]` (message IDs)
- `history_watcher` — already uses TelegramQueue (no migration needed)

**Architecture notes (resolved during review):**

1. **Why poller starts immediately, but watcher doesn't:**
   - Poller works with tmux directly (doesn't need session_id)
   - Watcher needs session_id + jsonl_path (set during binding)
   - Binding requires `last_sent_message` (set when user sends first message)

2. **Why we don't start binding_task in launch_with_animation:**
   - `poll_for_session_thread` requires `thread.last_sent_message` (line 265)
   - On fresh launch, `last_sent_message = None` → function returns immediately
   - Binding happens naturally when user sends first message (bot.py:1430-1437)

3. **No poller duplication:**
   - Both `_start_monitoring` and `poll_for_session_thread` check:
     `if not thread.poller_task or thread.poller_task.done():`
   - If poller already running, second start is skipped

---

## Task 1: Add launch_task field to ThreadInfo

**Files:**
- Modify: `src/codogram/session_manager.py`

**Step 1: Add launch_task field**

Find ThreadInfo dataclass and add after binding_task:

```python
launch_task: asyncio.Task | None = field(default=None, repr=False)
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/session_manager.py`
Expected: No errors

**Step 3: Run existing tests**

Run: `pytest tests/test_session_manager.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/codogram/session_manager.py
git commit -m "feat(session_manager): add launch_task field to ThreadInfo"
```

---

## Task 2: Add EditBatch to TelegramQueue

**Files:**
- Modify: `src/codogram/telegram_queue.py`
- Create: `tests/test_telegram_queue_edit.py`

**Step 1: Add EditBatch dataclass**

```python
@dataclass
class EditBatch:
    """Single message edit operation."""
    chat_id: int
    message_id: int
    text: str
    parse_mode: str | None = None
```

**Step 2: Update QueueItem type**

```python
QueueItem = OutgoingBatch | EditBatch
```

**Step 3: Add _edit_message method**

Handle edits with retry on Markdown errors (like _send_batch).

**Step 4: Update _process_item to handle EditBatch**

**Step 5: Write test**

```python
@pytest.mark.asyncio
async def test_edit_batch():
    # Test that EditBatch is processed correctly
    pass
```

**Step 6: Verify and commit**

```bash
python3 -m py_compile src/codogram/telegram_queue.py
pytest tests/test_telegram_queue_edit.py -v
git add src/codogram/telegram_queue.py tests/test_telegram_queue_edit.py
git commit -m "feat(telegram_queue): add EditBatch support"
```

---

## Task 3: Create launch_animation module with FACES

**Files:**
- Create: `src/codogram/launch_animation.py`
- Create: `tests/test_launch_animation.py`

**Step 1: Write test for FACES constant**

```python
# tests/test_launch_animation.py
from codogram.launch_animation import FACES, FACE_READY

def test_faces_are_unique():
    assert len(FACES) == len(set(FACES))

def test_face_ready_not_in_faces():
    assert FACE_READY not in FACES
```

**Step 2: Run test (should fail)**

Run: `pytest tests/test_launch_animation.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create launch_animation.py with constants only**

```python
# src/codogram/launch_animation.py
"""Background launch animation for Claude sessions."""

FACES = [
    "[._.]",   # Sleeping
    "[-_-]",   # Waking
    "[.o.]",   # Alert
    "[o_o]",   # Watching
    "[◉_◉]",   # Focused
    "[◉︿◉]",  # Tense
    "[°_°]",   # Confused
    "[°□°]",   # Shocked
    "[ಠ_ಠ]",   # Frustrated
    "[ಠ益ಠ]",  # Angry
    "[>_<]",   # Panic
    "[×_×]",   # Overload
    "[☠_☠]",   # Dead
]

FACE_READY = "[≖‿≖]"
```

**Step 4: Run test (should pass)**

Run: `pytest tests/test_launch_animation.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/launch_animation.py tests/test_launch_animation.py
git commit -m "feat(launch_animation): add faces constants"
```

---

## Task 4: Implement launch_with_animation with monitoring

**Files:**
- Modify: `src/codogram/launch_animation.py`

**NOTE:** This task includes both the main function AND the `_start_monitoring` helper to avoid py_compile errors from undefined references.

**Step 1: Add imports**

```python
import asyncio
import time

from aiogram import Bot

from .logging_config import logger
from .session_manager import ProjectState, ThreadInfo, project_manager
from .telegram_queue import TelegramQueue, EditBatch
from .tmux import TmuxSession
```

**Step 2: Add _start_monitoring helper FIRST**

```python
async def _start_monitoring(
    bot: Bot,
    project: ProjectState,
    thread: ThreadInfo,
    queue: TelegramQueue,
):
    """Start poller after successful Claude launch.

    NOTE: We only start poller here, NOT binding_task/watcher because:
    - poll_for_session_thread requires last_sent_message (line 265)
    - On fresh launch, last_sent_message = None → returns immediately
    - Binding happens when user sends first message (bot.py:1430-1437)
    - poll_for_session_thread will start watcher when session is found

    Poller can start immediately because it works with tmux directly,
    doesn't need session_id or jsonl_path.

    No duplication risk: poll_for_session_thread checks
    `if not thread.poller_task or thread.poller_task.done():`
    before starting poller (history_watcher.py:301).
    """
    from .permission_poller import create_poller_task_for_thread

    if not thread.poller_task or thread.poller_task.done():
        thread.poller_task = await create_poller_task_for_thread(
            bot, project, thread, queue
        )
```

**Step 3: Add launch_with_animation function**

Key points:
- Block session discovery: `thread.awaiting_new_session = True`
- Send status messages
- Create tmux and run `claude`
- Wait for ready with face animation after 3 sec
- **Timeout → error message, return False**
- Start poller only (watcher starts later via user message → binding)
- Save state on success (not in finally — only save on actual state change)

```python
async def launch_with_animation(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
    project: ProjectState,
    thread: ThreadInfo,
    queue: TelegramQueue,
) -> bool:
    """Launch Claude with animated status messages."""
    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    try:
        thread.awaiting_new_session = True

        # 1. Create tmux
        await bot.send_message(chat_id, "Создаю tmux сессию...", message_thread_id=thread_id)

        if not tmux.exists():
            tmux.create()

        # 2. Launch Claude
        await bot.send_message(chat_id, "Запускаю Claude...", message_thread_id=thread_id)
        tmux.send("claude")

        # 3. Wait for ready with animation
        await bot.send_message(chat_id, "Жду готовность Claude...", message_thread_id=thread_id)

        start_time = time.time()
        face_msg = None
        face_idx = 0

        while not tmux.is_claude_ready():
            elapsed = time.time() - start_time

            # Timeout check FIRST
            if elapsed > 120:
                if face_msg:
                    try:
                        await bot.delete_message(chat_id, face_msg.message_id)
                    except Exception:
                        pass
                await bot.send_message(
                    chat_id, "❌ Таймаут: Claude не запустился за 2 минуты",
                    message_thread_id=thread_id
                )
                return False

            # Face animation
            if elapsed > 3 and face_msg is None:
                face_msg = await bot.send_message(
                    chat_id, f"`{FACES[0]}`",
                    parse_mode="Markdown",
                    message_thread_id=thread_id
                )
                face_idx = 1
            elif face_msg and face_idx < len(FACES):
                await queue.enqueue(EditBatch(
                    chat_id=chat_id,
                    message_id=face_msg.message_id,
                    text=f"`{FACES[face_idx]}`",
                    parse_mode="Markdown",
                ))
                face_idx += 1

            await asyncio.sleep(3)

        # 4. Success - cleanup face
        if face_msg:
            await queue.enqueue(EditBatch(
                chat_id=chat_id,
                message_id=face_msg.message_id,
                text=f"`{FACE_READY}`",
                parse_mode="Markdown",
            ))
            await asyncio.sleep(1.5)
            try:
                await bot.delete_message(chat_id, face_msg.message_id)
            except Exception:
                pass

        await bot.send_message(chat_id, "✓ Claude готов!", message_thread_id=thread_id)

        # 5. Start monitoring
        await _start_monitoring(bot, project, thread, queue)

        # 6. Save state on success
        project_manager._save()

        return True

    except Exception as e:
        logger.error(f"launch_error: {e}")
        try:
            await bot.send_message(chat_id, f"❌ Ошибка запуска: {e}", message_thread_id=thread_id)
        except Exception:
            pass
        return False

    finally:
        thread.awaiting_new_session = False
        thread.launch_task = None
```

**Step 4: Verify syntax**

Run: `python3 -m py_compile src/codogram/launch_animation.py`
Expected: No errors

**Step 5: Commit**

```bash
git add src/codogram/launch_animation.py
git commit -m "feat(launch_animation): implement launch_with_animation with monitoring"
```

---

## Task 5: Update bot.py to use background launch

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Update on_start_launch_claude callback**

```python
@router.callback_query(F.data == "start:launch_claude")
async def on_start_launch_claude(callback: CallbackQuery):
    # ... existing auth and state checks ...

    thread = project.get_or_create_thread(None, "main")

    # Race protection
    if thread.launch_task and not thread.launch_task.done():
        await callback.answer("⏳ Запуск уже идёт...")
        return

    await callback.answer()
    _start_state.pop(chat_id, None)

    from .launch_animation import launch_with_animation
    from .main import telegram_queue

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot,
            chat_id=chat_id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )

    project_manager._save()
```

**Step 2: Update launch_claude_in_thread similarly**

Add race protection and use launch_with_animation.

**Step 3: Verify and commit**

```bash
python3 -m py_compile src/codogram/bot.py
git add src/codogram/bot.py
git commit -m "feat(bot): use background launch with animation"
```

---

## Task 6: Migrate permission_poller keyboard sends to TelegramQueue

**Files:**
- Modify: `src/codogram/telegram_queue.py`
- Modify: `src/codogram/permission_poller.py`

**Context:** permission_poller uses TelegramQueue for content but `bot.send_message` directly for keyboards. This bypasses rate limiting.

**NOTE:** `enqueue()` already returns `list[int]` (message IDs), so KeyboardBatch will work the same way.

**Step 1: Add KeyboardBatch to telegram_queue.py**

```python
from aiogram.types import InlineKeyboardMarkup

@dataclass
class KeyboardBatch:
    """Keyboard message with reply markup."""
    chat_id: int
    text: str
    reply_markup: InlineKeyboardMarkup
    thread_id: int | None = None
```

**Step 2: Update QueueItem type**

```python
QueueItem = OutgoingBatch | EditBatch | KeyboardBatch
```

**Step 3: Add _send_keyboard method**

```python
async def _send_keyboard(self, batch: KeyboardBatch) -> list[int]:
    """Send keyboard message."""
    try:
        msg = await self.bot.send_message(
            batch.chat_id,
            batch.text,
            reply_markup=batch.reply_markup,
            message_thread_id=batch.thread_id,
        )
        return [msg.message_id]
    except Exception as e:
        logger.error(f"keyboard_send_error: {e}")
        return []
```

**Step 4: Update _process_item to handle KeyboardBatch**

**Step 5: Update permission_poller**

Replace (4 occurrences):
```python
kb_msg = await bot.send_message(chat_id, "👆", reply_markup=kb)
```

With:
```python
kb_msg_ids = await telegram_queue.enqueue(KeyboardBatch(
    chat_id=chat_id,
    text="👆",
    reply_markup=kb,
    thread_id=thread_id,
))
kb_msg_id = kb_msg_ids[0] if kb_msg_ids else None
```

**Step 6: Update cleanup code to use kb_msg_id instead of kb_msg.message_id**

**Step 7: Verify and commit**

```bash
python3 -m py_compile src/codogram/telegram_queue.py
python3 -m py_compile src/codogram/permission_poller.py
pytest tests/ -v
git add src/codogram/telegram_queue.py src/codogram/permission_poller.py
git commit -m "refactor(poller): migrate keyboard sends to TelegramQueue"
```

---

## Task 7: Add tests for launch_with_animation

**Files:**
- Create: `tests/test_launch_animation_function.py`

**Step 1: Test race condition protection**

```python
@pytest.mark.asyncio
async def test_launch_blocks_concurrent_launch():
    """Second launch attempt returns early if launch_task is running."""
    # Mock thread with running launch_task
    # Verify function returns False or raises
```

**Step 2: Test timeout behavior**

```python
@pytest.mark.asyncio
async def test_launch_timeout_shows_error():
    """After 120s timeout, shows error message and returns False."""
    # Mock tmux.is_claude_ready() to always return False
    # Use monkeypatch to set short timeout
    # Verify error message sent
    # Verify returns False
```

**Step 3: Test successful launch**

```python
@pytest.mark.asyncio
async def test_launch_success_starts_poller():
    """Successful launch starts poller only."""
    # Mock tmux.is_claude_ready() to return True immediately
    # Verify poller_task is started
    # Verify binding_task is NOT started (happens on first user message)
    # Verify returns True
```

**Step 4: Run tests and commit**

```bash
pytest tests/test_launch_animation_function.py -v
git add tests/test_launch_animation_function.py
git commit -m "test(launch_animation): add function tests"
```

---

## Task 8: Manual testing and fixes

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 2: Manual test**

1. Restart bot: `./restart.sh`
2. Send `/start` in Telegram
3. Click "Да, запустить"
4. Verify:
   - Status messages appear sequentially
   - Face animation starts after 3 seconds (if Claude not ready)
   - Other messages can be sent during launch
   - "✓ Claude готов!" appears when ready
   - Poller and watcher start working

**Step 3: Commit any fixes**

---

## Task 9: Cleanup

**Step 1: Remove unused code**

Delete old `launch_claude_new` if exists.

**Step 2: Update stale comments**

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: cleanup old launch code"
```

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 1 | Add launch_task to ThreadInfo | TODO |
| 2 | Add EditBatch to TelegramQueue | TODO |
| 3 | Create launch_animation with FACES | TODO |
| 4 | Implement launch_with_animation + _start_monitoring | TODO |
| 5 | Update bot.py to use animation | TODO |
| 6 | Migrate poller keyboards to queue | TODO |
| 7 | Add tests for launch_with_animation | TODO |
| 8 | Manual testing and fixes | TODO |
| 9 | Cleanup | TODO |

**Notes:**
- Tasks reduced from 10 to 9 by merging Task 4+5
- `history_watcher` already uses TelegramQueue — no migration needed
- `project_manager._save()` is the existing pattern in codebase (not ideal but consistent)

**Architectural decisions (see header for details):**
- `_start_monitoring` starts only poller, not binding_task
- Watcher starts later when user sends first message (triggers binding)
- No poller duplication due to guards in both places
