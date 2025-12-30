# src/codogram/launch_animation.py
"""Background launch animation for Claude sessions."""

import asyncio
import time

from aiogram import Bot

from .logging_config import logger
from .session_manager import ProjectState, ThreadInfo, project_manager
from .telegram_queue import TelegramQueue, EditBatch
from .tmux import TmuxSession

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
        thread.start_requested_at = time.time()

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

            # Debug: log what we see in tmux every 10 seconds
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                pane_content = tmux.capture_pane()
                logger.debug(f"launch_wait: elapsed={elapsed:.0f}s, pane_preview={pane_content[-200:] if pane_content else 'empty'}")

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

        await bot.send_message(
            chat_id,
            f"✓ Claude готов!\nПодключиться: `tmux attach -t {tmux_name}`",
            parse_mode="Markdown",
            message_thread_id=thread_id
        )

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
