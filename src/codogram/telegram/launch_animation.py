# src/codogram/telegram/launch_animation.py
"""Background launch animation for Claude sessions."""

import asyncio
import time

from aiogram import Bot

from .. import strings
from ..config import settings
from ..logging_config import logger
from ..claude.screen import parse_screen, PermissionPrompt
from ..services.start_flow import build_announcement, build_thread_announcement
from ..core.session_manager import ProjectState, ThreadInfo, project_manager
from .queue import TelegramQueue, EditBatch
from ..tmux.session import TmuxSession

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
    """Start poller and watcher after successful Claude launch.

    For NEW sessions: only starts poller. Watcher starts when session is bound
    (after user sends first message and we find matching jsonl).

    For RESUMED sessions: starts both poller AND watcher immediately,
    since we already have session_id and jsonl_path.
    """
    from ..claude.poller import create_poller_task_for_thread
    from ..claude.history_watcher import watch_thread_jsonl

    # Always start poller (works with tmux directly)
    if not thread.poller_task or thread.poller_task.done():
        thread.poller_task = await create_poller_task_for_thread(
            bot, project, thread, queue
        )

    # For resumed sessions, also start watcher immediately
    if thread.session_id and thread.jsonl_path:
        if not thread.watcher_task or thread.watcher_task.done():
            thread.watcher_task = asyncio.create_task(
                watch_thread_jsonl(bot, project, thread, queue)
            )


async def launch_with_animation(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
    project: ProjectState,
    thread: ThreadInfo,
    queue: TelegramQueue,
    session_id: str | None = None,
    cwd: str | None = None,
) -> bool:
    """Launch Claude with animated status messages.

    Args:
        session_id: If provided, uses 'claude --resume {session_id}' instead of 'claude'
        cwd: If provided, uses this directory instead of project.cwd for the tmux session
    """
    actual_cwd = cwd or project.cwd
    if not actual_cwd:
        await queue.send(
            chat_id,
            strings.LAUNCH_PROJECT_CWD_NOT_SET,
            thread_id=thread_id,
            parse_mode="MarkdownV2",
        )
        return False

    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, actual_cwd)

    try:
        thread.awaiting_new_session = True
        thread.start_requested_at = time.time()
        thread.notified_closed = False  # Reset so we can notify again if this session dies

        # 1. Create tmux
        await queue.send(chat_id, strings.LAUNCH_CREATING_TMUX, thread_id=thread_id, parse_mode="MarkdownV2")

        if not tmux.exists():
            tmux.create()

        # 2. Launch Claude
        if session_id:
            await queue.send(chat_id, strings.LAUNCH_RESUMING, thread_id=thread_id, parse_mode="MarkdownV2")
            tmux.send(f"claude --resume {session_id}")
        else:
            await queue.send(chat_id, strings.LAUNCH_STARTING, thread_id=thread_id, parse_mode="MarkdownV2")
            tmux.send("claude")

        # 2.5. Start poller early to catch trust prompts during startup
        await _start_monitoring(bot, project, thread, queue)

        # 3. Wait for ready with animation
        await queue.send(chat_id, strings.LAUNCH_WAITING, thread_id=thread_id, parse_mode="MarkdownV2")

        start_time = time.time()
        face_msg_id: int | None = None
        face_idx = 0

        while True:
            # Check if Claude UI is fully loaded
            if tmux.is_claude_ready():
                break

            # Also check if a prompt is showing (Claude is running, waiting for user)
            pane_content = tmux.capture_pane()
            parsed = parse_screen(pane_content)
            if isinstance(parsed, PermissionPrompt):
                logger.info(f"launch_ready_via_prompt: type={parsed.prompt_type.value}")
                break

            elapsed = time.time() - start_time

            # Debug: log what we see in tmux every 10 seconds
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                logger.debug(f"launch_wait: elapsed={elapsed:.0f}s, pane_preview={pane_content[-200:] if pane_content else 'empty'}")

            # Timeout check
            if elapsed > settings.claude_launch_timeout:
                if face_msg_id:
                    try:
                        await bot.delete_message(chat_id, face_msg_id)
                    except Exception:
                        pass
                await queue.send(
                    chat_id, strings.LAUNCH_TIMEOUT,
                    thread_id=thread_id,
                    parse_mode="MarkdownV2"
                )
                return False

            # Face animation
            if elapsed > 3 and face_msg_id is None:
                sent_ids = await queue.send(
                    chat_id, f"`{FACES[0]}`",
                    thread_id=thread_id,
                    parse_mode="MarkdownV2",
                )
                face_msg_id = sent_ids[0] if sent_ids else None
                face_idx = 1
            elif face_msg_id:
                await queue.enqueue(EditBatch(
                    chat_id=chat_id,
                    message_id=face_msg_id,
                    text=f"`{FACES[face_idx % len(FACES)]}`",
                    parse_mode="MarkdownV2",
                ))
                face_idx += 1

            await asyncio.sleep(3)

        # 4. Success - cleanup face
        if face_msg_id:
            await queue.enqueue(EditBatch(
                chat_id=chat_id,
                message_id=face_msg_id,
                text=f"`{FACE_READY}`",
                parse_mode="MarkdownV2",
            ))
            await asyncio.sleep(1.5)
            try:
                await bot.delete_message(chat_id, face_msg_id)
            except Exception:
                pass

        # Build announcement: full for General, short for topics
        if thread_id is None:
            # General - full announcement with commands
            try:
                chat = await bot.get_chat(chat_id)
                is_forum = chat.is_forum or False
            except Exception:
                is_forum = False
            announcement = build_announcement(project.project_name, tmux_name, is_forum)
        else:
            # Topic - short announcement
            announcement = build_thread_announcement(thread.name, tmux_name)
            # Add emoji pack hint if feature enabled
            if project.feat_avatar_pack and project.emoji_pack_name:
                pack_link = f"https://t.me/addemoji/{project.emoji_pack_name}"
                announcement += f"\n\n{strings.EMOJI_PACK_TOPIC_HINT.format(pack_link=pack_link)}"
        logger.info(f"launch_sending_announcement: project={project.project_name}")
        try:
            await queue.send(
                chat_id,
                announcement,
                thread_id=thread_id,
                parse_mode="MarkdownV2",
            )
            logger.info(f"launch_announcement_sent: project={project.project_name}")
        except Exception as e:
            logger.error(f"launch_announcement_failed: {e}")

        # 5. Start monitoring
        await _start_monitoring(bot, project, thread, queue)

        # 6. Save state on success
        project_manager._save()

        return True

    except Exception as e:
        logger.error(f"launch_error: {e}")
        try:
            await queue.send(chat_id, strings.LAUNCH_ERROR.format(error=e), thread_id=thread_id, parse_mode="MarkdownV2")
        except Exception:
            pass
        return False

    finally:
        thread.awaiting_new_session = False
        thread.launch_task = None
