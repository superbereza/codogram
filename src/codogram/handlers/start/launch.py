# src/codogram/handlers/start/launch.py
"""Launch helpers for start flow.

BUG FIXES applied:
- Silent returns -> user feedback messages
- Blocking subprocess.run -> asyncio.to_thread
- Race condition -> feedback if already launching
- worktree_recovery: pass session_id, reopen topic, restore icon
- "Resume in main" -> now launches Claude after archiving
"""
import asyncio
from pathlib import Path

from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from ... import strings
from ...core.session_manager import project_manager
from ...logging_config import logger
from ...services.start import FlowResult
from ...telegram.queue import TelegramQueue
from ...tmux.launcher import is_tmux_session_exists
from .helpers import register_chat_menu


async def launch_claude(msg: Message, result: FlowResult, queue: TelegramQueue):
    """Launch Claude session from message context."""
    from ...telegram.launch_animation import launch_with_animation

    project = project_manager.get_by_chat(msg.chat.id)
    if not project:
        # BUG FIX: Was silent return
        await queue.reply(msg, strings.PROJECT_NOT_FOUND, parse_mode=None)
        return

    await register_chat_menu(msg.bot, msg.chat)
    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        # BUG FIX: Was silent return
        await queue.reply(msg, strings.LAUNCH_IN_PROGRESS, parse_mode=None)
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=msg.bot,
            chat_id=msg.chat.id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=queue,
        )
    )


async def launch_claude_from_callback(cb: CallbackQuery, result: FlowResult, queue: TelegramQueue):
    """Launch Claude session from callback context."""
    from ...telegram.launch_animation import launch_with_animation

    project = project_manager.get_by_chat(cb.message.chat.id)
    if not project:
        # BUG FIX: Was silent return
        await cb.answer(strings.PROJECT_NOT_FOUND)
        return

    await register_chat_menu(cb.bot, cb.message.chat)
    thread = project.get_or_create_thread(None, "main")

    if thread.launch_task and not thread.launch_task.done():
        # BUG FIX: Was silent return
        await cb.answer(strings.LAUNCH_IN_PROGRESS)
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=cb.bot,
            chat_id=cb.message.chat.id,
            thread_id=None,
            project=project,
            thread=thread,
            queue=queue,
        )
    )


async def launch_claude_in_thread(msg: Message, result: FlowResult, queue: TelegramQueue):
    """Launch Claude in a specific thread."""
    from ...telegram.launch_animation import launch_with_animation
    from ...tmux.session import TmuxSession
    import subprocess

    project = project_manager.get_by_chat(msg.chat.id)
    if not project:
        # BUG FIX: Was silent return
        await queue.reply(msg, strings.PROJECT_NOT_FOUND, parse_mode=None)
        return

    thread = project.threads.get(result.thread_id)
    if not thread:
        # BUG FIX: Was silent return
        await queue.reply(msg, strings.THREAD_NOT_FOUND, parse_mode=None)
        return

    # Check if tmux already running
    tmux_name = thread.get_tmux_session(project.project_name)
    actual_cwd = thread.worktree_path or project.cwd

    if is_tmux_session_exists(tmux_name):
        tmux = TmuxSession(tmux_name, actual_cwd)
        if tmux.is_claude_ready():
            await queue.reply(msg, strings.START_ALREADY_RUNNING.format(tmux_name=tmux_name))
            return
        else:
            # BUG FIX: Was blocking subprocess.run
            await asyncio.to_thread(
                subprocess.run,
                ["tmux", "kill-session", "-t", tmux_name],
                capture_output=True
            )

    # Reopen topic and reset icon
    if result.thread_id:
        was_reopened = False
        try:
            await msg.bot.reopen_forum_topic(msg.chat.id, result.thread_id)
            logger.info(f"Topic {result.thread_id} reopened")
            was_reopened = True
        except Exception as e:
            # BUG FIX: Log instead of bare pass
            logger.debug(f"reopen_forum_topic failed (may be already open): {e}")

        if was_reopened:
            try:
                await msg.bot.edit_forum_topic(
                    msg.chat.id, result.thread_id,
                    icon_custom_emoji_id=strings.ICON_BALLOT_BOX  # BUG FIX: Use constant
                )
            except Exception as e:
                logger.warning(f"Failed to set topic icon: {e}")

        if thread.archived:
            thread.archived = False
            project_manager._save()

    if thread.launch_task and not thread.launch_task.done():
        # BUG FIX: Was silent return
        await queue.reply(msg, strings.LAUNCH_IN_PROGRESS, parse_mode=None)
        return

    # Check worktree/session validity
    cwd = thread.worktree_path if thread.has_valid_worktree() else None

    session_id = None
    if thread.has_valid_session():
        session_id = thread.session_id
    elif thread.session_id and not thread.has_valid_session():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Start new session",
                                  callback_data=f"resume:start_new:{result.thread_id}")],
            [InlineKeyboardButton(text=strings.BTN_CANCEL,
                                  callback_data=f"resume:cancel:{result.thread_id}")]
        ])
        await queue.reply(msg, strings.START_SESSION_NOT_FOUND, reply_markup=keyboard)
        return

    if thread.worktree_path and not thread.has_valid_worktree():
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Recreate worktree",
                                  callback_data=f"resume:recreate:{result.thread_id}")],
            [InlineKeyboardButton(text=strings.BTN_CANCEL,
                                  callback_data=f"resume:cancel:{result.thread_id}")]
        ])
        await queue.reply(msg, strings.START_WORKTREE_NOT_FOUND.format(path=thread.worktree_path),
                          reply_markup=keyboard)
        return

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=msg.bot, chat_id=msg.chat.id, thread_id=result.thread_id,
            project=project, thread=thread, queue=queue,
            session_id=session_id, cwd=cwd,
        )
    )


# === Worktree Recovery Handlers (merged from worktree_recovery.py) ===

async def handle_wr_recreate(callback: CallbackQuery, queue: TelegramQueue):
    """Recreate worktree from existing branch.

    BUG FIXES: pass session_id, reopen topic, restore icon
    """
    from ...services.branch import create_worktree
    from ...telegram.launch_animation import launch_with_animation

    await callback.answer()
    thread_id = _parse_thread_id(callback.data)
    if thread_id is None:
        await queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
        return

    success, path = create_worktree(Path(project.cwd), thread.name)
    if not success:
        await queue.edit(callback.message, strings.WORKTREE_RECREATE_FAILED.format(path=path))
        return

    thread.worktree_path = path
    project_manager._save()
    await callback.message.delete()

    # BUG FIX: Reopen topic and restore icon
    try:
        await callback.bot.reopen_forum_topic(callback.message.chat.id, thread_id)
    except Exception as e:
        logger.debug(f"reopen_forum_topic failed: {e}")

    try:
        await callback.bot.edit_forum_topic(
            callback.message.chat.id, thread_id,
            icon_custom_emoji_id=strings.ICON_BALLOT_BOX
        )
    except Exception as e:
        logger.warning(f"Failed to set topic icon: {e}")

    if thread.archived:
        thread.archived = False
        project_manager._save()

    # BUG FIX: Pass session_id if valid
    session_id = thread.session_id if thread.has_valid_session() else None

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot, chat_id=callback.message.chat.id,
            thread_id=thread_id, project=project, thread=thread,
            queue=queue, cwd=path, session_id=session_id,
        )
    )


async def handle_wr_create(callback: CallbackQuery, queue: TelegramQueue):
    """Create new branch and worktree."""
    from ...services.branch import create_branch_with_worktree
    from ...telegram.launch_animation import launch_with_animation

    await callback.answer()
    thread_id = _parse_thread_id(callback.data)
    if thread_id is None:
        await queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
        return

    success, path = create_branch_with_worktree(Path(project.cwd), thread.name)
    if not success:
        await queue.edit(callback.message, strings.WORKTREE_BRANCH_CREATE_FAILED.format(path=path))
        return

    thread.worktree_path = path
    project_manager._save()
    await callback.message.delete()

    # BUG FIX: Reopen topic and restore icon
    try:
        await callback.bot.reopen_forum_topic(callback.message.chat.id, thread_id)
    except Exception as e:
        logger.debug(f"reopen_forum_topic failed: {e}")

    try:
        await callback.bot.edit_forum_topic(
            callback.message.chat.id, thread_id,
            icon_custom_emoji_id=strings.ICON_BALLOT_BOX
        )
    except Exception as e:
        logger.warning(f"Failed to set topic icon: {e}")

    if thread.archived:
        thread.archived = False
        project_manager._save()

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot, chat_id=callback.message.chat.id,
            thread_id=thread_id, project=project, thread=thread,
            queue=queue, cwd=path,
        )
    )


async def handle_wr_main(callback: CallbackQuery, queue: TelegramQueue):
    """Resume in main by archiving topic, then launch Claude in main.

    BUG FIX: Original just archived topic without launching Claude!
    """
    from ...services.branch import archive_thread
    from ...telegram.launch_animation import launch_with_animation

    await callback.answer()
    thread_id = _parse_thread_id(callback.data)
    if thread_id is None:
        await queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
        return

    project = project_manager.get_by_chat(callback.message.chat.id)
    if not project:
        await queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
        return

    thread = project.get_thread(thread_id)
    if not thread:
        await queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
        return

    # Archive the topic
    await archive_thread(callback.bot, callback.message.chat.id, project, thread)
    await queue.edit(callback.message, strings.WORKTREE_TOPIC_ARCHIVED)

    # BUG FIX: Launch Claude in main thread
    main_thread = project.get_or_create_thread(None, "main")
    session_id = main_thread.session_id if main_thread.has_valid_session() else None

    main_thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot, chat_id=callback.message.chat.id,
            thread_id=None, project=project, thread=main_thread,
            queue=queue, cwd=project.cwd, session_id=session_id,
        )
    )


async def handle_wr_cancel(callback: CallbackQuery, queue: TelegramQueue):
    """Cancel recovery - just delete message."""
    await callback.answer()
    await callback.message.delete()


def _parse_thread_id(callback_data: str) -> int | None:
    """Parse thread_id from callback data like 'wr_recreate:123'."""
    try:
        return int(callback_data.split(":")[1])
    except (IndexError, ValueError):
        return None
