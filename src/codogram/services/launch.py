# src/codogram/services/launch.py
"""Launch service for creating threads with Claude sessions."""
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot

if TYPE_CHECKING:
    from ..telegram_queue import TelegramQueue

from ..session_manager import ProjectState, ThreadInfo, project_manager
from ..launch_animation import launch_with_animation
from ..logging_config import logger


async def create_thread_with_session(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    name: str,
    create_worktree: bool = False,
    base_branch: str | None = None,
) -> ThreadInfo | None:
    """
    Create Telegram topic + ThreadInfo + (optionally) worktree + launch Claude.

    Unified entry point for /thread_create and /branch_create.
    Topic is created FIRST, so all status messages go to the new topic.

    Args:
        bot: Telegram bot instance
        chat_id: Telegram chat ID
        project: Project state
        name: Thread/branch name (will be capitalized for topic title)
        create_worktree: If True, create git worktree before launching Claude
        base_branch: Base branch for worktree (required if create_worktree=True)

    Returns:
        ThreadInfo if successful, None if failed
    """
    # 1. Create Telegram topic FIRST
    try:
        topic = await bot.create_forum_topic(chat_id, name.capitalize())
    except Exception as e:
        logger.error(f"Failed to create forum topic: {e}")
        return None

    thread_id = topic.message_thread_id

    # Create ThreadInfo early so we can send messages to the topic
    topic_display_name = name.capitalize()
    thread = ThreadInfo(thread_id=thread_id, name=name, topic_name=topic_display_name)
    thread.base_branch = base_branch
    project.threads[thread_id] = thread
    project_manager._save()

    # 3. Launch Claude with animation
    from ..main import telegram_queue

    # 2. Create worktree if requested
    worktree_path: str | None = None
    if create_worktree:
        worktree_path = await _create_worktree_with_status(
            telegram_queue, chat_id, thread_id, project, name, base_branch
        )
        if worktree_path is None:
            # Failed - topic exists but no worktree/claude
            return None
        thread.worktree_path = worktree_path
        project_manager._save()

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


async def _create_worktree_with_status(
    telegram_queue: "TelegramQueue",
    chat_id: int,
    thread_id: int,
    project: ProjectState,
    branch_name: str,
    base_branch: str | None,
) -> str | None:
    """
    Create git worktree with status messages in the topic.

    Returns worktree path on success, None on failure.
    """
    from ..worktree import create_worktree

    main_repo = Path(project.cwd)
    # Worktree inside .worktrees/ subdirectory
    worktree_path = main_repo / ".worktrees" / branch_name

    # Ensure .worktrees/ directory exists before creating worktree
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Status: creating branch
    await telegram_queue.send(
        chat_id,
        f"`[~]` Creating branch `{branch_name}` from `{base_branch}`...",
        thread_id=thread_id,
        parse_mode="MarkdownV2"
    )

    # Create worktree (includes branch creation)
    result = create_worktree(main_repo, worktree_path, branch_name, base_branch)

    if not result.success:
        await telegram_queue.send(
            chat_id,
            f"`[x]` {result.error}",
            thread_id=thread_id,
            parse_mode="MarkdownV2"
        )
        return None

    # Status: worktree created
    await telegram_queue.send(
        chat_id,
        f"`[v]` Worktree: `{worktree_path}`",
        thread_id=thread_id,
        parse_mode="MarkdownV2"
    )

    return str(worktree_path)
