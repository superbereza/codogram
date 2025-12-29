# Background Launch Animation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Non-blocking Claude launch with animated status messages.

**Architecture:** Background task for launch, text statuses, face animation if waiting > 3 sec, all edits through TelegramQueue.

**Tech Stack:** Python 3.11+, asyncio, aiogram 3.x, pytest

**Design:** [docs/designs/2025-12-29-background-launch-animation.md](../designs/2025-12-29-background-launch-animation.md)

---

## Task 1: TelegramQueue with OutgoingBatch ✅ DONE

Already implemented in earlier session. See `src/codogram/telegram_queue.py`.

---

## Task 2: Add EditBatch to TelegramQueue ✅ DONE

Already implemented. Commit: `69abc7a feat(telegram_queue): add EditBatch support for message editing`

---

## Task 3: Add launch_task field to ThreadInfo

**Files:**
- Modify: `src/codogram/session_manager.py`

**Step 1: Add launch_task field**

Find ThreadInfo dataclass in session_manager.py and add:

```python
@dataclass
class ThreadInfo:
    thread_id: int | None
    name: str
    session_id: str | None = None
    jsonl_path: str | None = None
    last_sent_message: str | None = None
    awaiting_new_session: bool = False
    watcher_task: asyncio.Task | None = None
    poller_task: asyncio.Task | None = None
    binding_task: asyncio.Task | None = None
    launch_task: asyncio.Task | None = None  # NEW
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

## Task 4: Create launch_animation module with FACES

**Files:**
- Create: `src/codogram/launch_animation.py`
- Create: `tests/test_launch_animation.py`

**Step 1: Write test for FACES constant**

```python
# tests/test_launch_animation.py
from codogram.launch_animation import FACES, FACE_READY

def test_faces_are_unique():
    """All faces in FACES list are unique."""
    assert len(FACES) == len(set(FACES))

def test_face_ready_not_in_faces():
    """FACE_READY is distinct from animation faces."""
    assert FACE_READY not in FACES
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_launch_animation.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create launch_animation.py**

```python
# src/codogram/launch_animation.py
"""Background launch animation for Claude sessions."""
import asyncio
import time

from aiogram import Bot

from .logging_config import logger
from .session_manager import ProjectState, ThreadInfo
from .telegram_queue import TelegramQueue, EditBatch
from .tmux import TmuxSession, create_tmux_with_claude


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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_launch_animation.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/launch_animation.py tests/test_launch_animation.py
git commit -m "feat(launch_animation): add faces constants"
```

---

## Task 5: Implement launch_with_animation function

**Files:**
- Modify: `src/codogram/launch_animation.py`

**Step 1: Add launch_with_animation function**

Append to `src/codogram/launch_animation.py`:

```python
async def launch_with_animation(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
    project: ProjectState,
    thread: ThreadInfo,
    queue: TelegramQueue,
    start_poller,
    start_watcher,
) -> bool:
    """Launch Claude with animated status messages.

    Returns True if successful, False otherwise.
    """
    tmux_name = thread.get_tmux_session(project.project_name)

    try:
        # Block session discovery during startup
        thread.awaiting_new_session = True

        # 1. Status messages
        await bot.send_message(
            chat_id, "Создаю tmux сессию...",
            message_thread_id=thread_id
        )

        result = create_tmux_with_claude(tmux_name, project.cwd)
        if not result.success:
            await bot.send_message(
                chat_id, f"❌ Ошибка: {result.error}",
                message_thread_id=thread_id
            )
            return False

        await bot.send_message(
            chat_id, "Запускаю Claude...",
            message_thread_id=thread_id
        )

        await bot.send_message(
            chat_id, "Жду готовность Claude...",
            message_thread_id=thread_id
        )

        # 2. Wait for ready, animate if > 3 sec
        tmux = TmuxSession(tmux_name, project.cwd)
        start_time = time.time()
        face_msg = None
        face_idx = 0

        while not tmux.is_claude_ready():
            elapsed = time.time() - start_time

            if elapsed > 3 and face_msg is None:
                # First face
                face_msg = await bot.send_message(
                    chat_id, f"`{FACES[0]}`",
                    parse_mode="Markdown",
                    message_thread_id=thread_id
                )
                face_idx = 1

            elif face_msg and face_idx < len(FACES):
                # Next face through queue
                await queue.enqueue(EditBatch(
                    chat_id=chat_id,
                    message_id=face_msg.message_id,
                    text=f"`{FACES[face_idx]}`",
                    parse_mode="Markdown",
                ))
                face_idx += 1

            await asyncio.sleep(3)

            if elapsed > 120:  # Timeout 2 min
                break

        # 3. Finish
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

        await bot.send_message(
            chat_id, "✓ Claude готов!",
            message_thread_id=thread_id
        )

        # 4. Start poller/watcher
        # TODO: Integrate with session binding

        return True

    except Exception as e:
        logger.error(f"launch_error: {e}")
        try:
            await bot.send_message(
                chat_id, f"❌ Ошибка запуска: {e}",
                message_thread_id=thread_id
            )
        except Exception:
            pass
        return False

    finally:
        thread.awaiting_new_session = False
        thread.launch_task = None
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/launch_animation.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/launch_animation.py
git commit -m "feat(launch_animation): implement launch_with_animation"
```

---

## Task 6: Update on_start_launch_claude to use background launch

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Find and update on_start_launch_claude callback**

Find the callback handler for `start:launch_claude` and update it to:
1. Get or create thread
2. Check if launch already in progress
3. Launch in background task

Key changes:
```python
# Get or create main thread
thread = project.get_or_create_thread(None, "main")

# Check if launch already in progress
if thread.launch_task and not thread.launch_task.done():
    await callback.answer("⏳ Запуск уже идёт...")
    return

# Import here to avoid circular imports
from .launch_animation import launch_with_animation
from .main import telegram_queue

# Launch in background
thread.launch_task = asyncio.create_task(
    launch_with_animation(
        bot=callback.bot,
        chat_id=chat_id,
        thread_id=None,
        project=project,
        thread=thread,
        queue=telegram_queue,
        start_poller=start_poller,
        start_watcher=start_watcher,
    )
)
```

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/bot.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): use background launch with animation"
```

---

## Task 7: Update launch_claude_in_thread to use animation

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Update launch_claude_in_thread function**

Find `launch_claude_in_thread` and update to use animation:
1. Check if launch already in progress
2. Launch in background task
3. Wait for completion (backwards compatibility)

**Step 2: Verify syntax**

Run: `python3 -m py_compile src/codogram/bot.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): use launch_with_animation in launch_claude_in_thread"
```

---

## Task 8: Run all tests and manual verification

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

---

## Task 9: Final cleanup

**Step 1: Remove old animation code from bot.py**

Delete the old `launch_claude_new` function if it exists and is unused.

**Step 2: Commit**

```bash
git add -A
git commit -m "chore: cleanup old launch code"
```

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 1 | TelegramQueue with OutgoingBatch | ✅ DONE |
| 2 | Add EditBatch to TelegramQueue | ✅ DONE |
| 3 | Add launch_task to ThreadInfo | TODO |
| 4 | Create launch_animation module | TODO |
| 5 | Implement launch_with_animation | TODO |
| 6 | Update on_start_launch_claude | TODO |
| 7 | Update launch_claude_in_thread | TODO |
| 8 | Run tests and verify | TODO |
| 9 | Cleanup | TODO |
