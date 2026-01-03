# src/codogram/services/launch.py
"""Launch service for creating threads with Claude sessions."""
import asyncio
from pathlib import Path

from aiogram import Bot

from ..session_manager import ProjectState, ThreadInfo, project_manager
from ..launch_animation import launch_with_animation
from ..logging_config import logger


async def create_thread_with_session(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    name: str,
    worktree_path: str | None = None,
    base_branch: str | None = None,
) -> ThreadInfo | None:
    """
    Create Telegram topic + ThreadInfo + launch Claude.

    Used by both /thread_create and /branch_create.

    Args:
        bot: Telegram bot instance
        chat_id: Telegram chat ID
        project: Project state
        name: Thread name (will be capitalized for topic title)
        worktree_path: Optional path to git worktree (if None, uses project.cwd)
        base_branch: Optional base branch name for worktree

    Returns:
        ThreadInfo if successful, None if failed
    """
    # Create Telegram topic
    try:
        topic = await bot.create_forum_topic(chat_id, name.capitalize())
    except Exception as e:
        logger.error(f"Failed to create forum topic: {e}")
        return None

    thread_id = topic.message_thread_id

    # Create ThreadInfo with worktree fields
    topic_display_name = name.capitalize()  # Same as passed to create_forum_topic
    thread = ThreadInfo(thread_id=thread_id, name=name, topic_name=topic_display_name)
    thread.worktree_path = worktree_path
    thread.base_branch = base_branch
    project.threads[thread_id] = thread
    project_manager._save()

    # Determine cwd for Claude - use worktree_path if provided
    cwd = worktree_path if worktree_path else project.cwd

    # Launch Claude with animation
    from ..main import telegram_queue

    # Race protection: check if launch already in progress
    if thread.launch_task and not thread.launch_task.done():
        logger.warning(f"Launch already in progress for thread {name}")
        return thread

    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=bot,
            chat_id=chat_id,
            thread_id=thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )

    project_manager._save()

    return thread
