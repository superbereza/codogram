# src/codogram/claude/poller/poller.py
"""Main poller loop - orchestrates all processors."""
import asyncio
from typing import TYPE_CHECKING

from aiogram import Bot

if TYPE_CHECKING:
    from ...telegram.queue import TelegramQueue

from .context import PollerContext
from .crash import detect_crash
from .processors import (
    AskUserQuestionProcessor,
    CompactProcessor,
    ThinkingProcessor,
    SuggestionsProcessor,
    StuckProcessor,
    PermissionProcessor,
)
from ...core.session_manager import ProjectState, ThreadInfo, project_manager
from ...tmux.session import TmuxSession
from ...telegram.queue import OutgoingBatch
from ...logging_config import logger
from ...config import settings
from ... import strings


async def create_poller_task(
    bot: Bot, project: ProjectState, telegram_queue: "TelegramQueue"
) -> asyncio.Task:
    """Create permission poller task for project (no thread)."""
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=None))


async def create_poller_task_for_thread(
    bot: Bot, project: ProjectState, thread: ThreadInfo, telegram_queue: "TelegramQueue"
) -> asyncio.Task:
    """Create permission poller task for a specific thread."""
    return asyncio.create_task(permission_poller(bot, project, telegram_queue, thread=thread))


async def permission_poller(
    bot: Bot,
    project: ProjectState,
    telegram_queue: "TelegramQueue",
    thread: ThreadInfo | None = None,
) -> None:
    """Background poller for permission prompts and status updates.

    Polls tmux every interval, delegates to processors.
    """
    # Build context
    if thread:
        tmux_name = thread.get_tmux_session(project.project_name)
        thread_id = thread.thread_id
        log_prefix = f"Thread poller [{thread.name}]"
        context_name = thread.name
    else:
        tmux_name = project.tmux_session
        thread_id = None
        log_prefix = "Poller"
        context_name = project.project_name

    logger.info(f"{log_prefix}: started for {context_name} (tmux: {tmux_name})")

    tmux = TmuxSession(tmux_name, project.cwd)

    ctx = PollerContext(
        bot=bot,
        project=project,
        thread=thread,
        tmux=tmux,
        queue=telegram_queue,
        chat_id=project.chat_id,
        thread_id=thread_id,
        log_prefix=log_prefix,
        context_name=context_name,
        tmux_name=tmux_name,
    )

    # Cleanup old suggestion message from previous session
    if thread and thread.last_suggestion_msg_id:
        try:
            await bot.delete_message(project.chat_id, thread.last_suggestion_msg_id)
            logger.info(f"{log_prefix}: cleaned up old suggestion msg {thread.last_suggestion_msg_id}")
        except Exception as e:
            logger.debug(f"{log_prefix}: failed to cleanup old suggestion: {e}")
        thread.last_suggestion_msg_id = None
        project_manager._save()

    # Initialize processors
    processors = [
        CompactProcessor(ctx),
        ThinkingProcessor(ctx),
        SuggestionsProcessor(ctx),
        StuckProcessor(ctx),
        PermissionProcessor(ctx),
        AskUserQuestionProcessor(ctx),
    ]

    poll_interval = settings.permission_poller_interval

    # Main loop
    while True:
        await asyncio.sleep(poll_interval)

        try:
            screen = tmux.capture_pane()
        except Exception as e:
            logger.warning(f"{log_prefix}: capture error: {e}")
            continue

        # Crash detection (exits poller)
        crash_reason = detect_crash(screen)
        if crash_reason:
            logger.error(f"{log_prefix}: Claude crashed! Reason: {crash_reason}")
            try:
                batch = OutgoingBatch(
                    chat_id=project.chat_id,
                    thread_id=thread_id,
                    messages=[{"text": strings.CLAUDE_CRASHED.format(reason=crash_reason), "parse_mode": "MarkdownV2"}],
                )
                await telegram_queue.enqueue_nowait(batch)
            except Exception:
                pass
            return

        # Process all processors
        for processor in processors:
            try:
                await processor.process(screen)
            except Exception as e:
                logger.warning(f"{log_prefix}: {processor.__class__.__name__} error: {e}")
