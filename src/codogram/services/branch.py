"""Branch/worktree operations."""
import subprocess
from pathlib import Path

from aiogram import Bot

from ..session_manager import project_manager, ProjectState, ThreadInfo
from ..worktree import remove_worktree
from ..logging_config import logger


async def do_branch_cleanup(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    thread: ThreadInfo,
    force: bool,
) -> None:
    """Clean up worktree, tmux, and archive topic.

    Args:
        bot: Telegram bot instance
        chat_id: Chat ID for the topic
        project: Project state
        thread: Thread to cleanup
        force: If True, force delete branch even if unmerged
    """
    main_repo = Path(project.cwd)
    worktree_path = Path(thread.worktree_path) if thread.worktree_path else None
    branch_name = thread.name

    # Cancel background tasks
    if thread.watcher_task:
        thread.watcher_task.cancel()
    if thread.poller_task:
        thread.poller_task.cancel()
    if thread.binding_task:
        thread.binding_task.cancel()

    # Kill tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Remove worktree and branch
    if worktree_path:
        remove_worktree(main_repo, worktree_path, branch_name, delete_branch=True, force=force)

    # Archive topic
    try:
        await bot.close_forum_topic(chat_id, thread.thread_id)
        await bot.edit_forum_topic(chat_id, thread.thread_id, icon_custom_emoji_id="5357315181649076022")
    except Exception:
        pass  # Topic may already be closed

    # Update thread state
    thread.archived = True
    thread.worktree_path = None
    thread.session_id = None
    project_manager._save()


async def do_branch_create(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    branch_name: str,
    base_branch: str,
) -> ThreadInfo | None:
    """Create topic + worktree + launch Claude.

    Returns:
        ThreadInfo if successful, None otherwise
    """
    from .launch import create_thread_with_session

    thread = await create_thread_with_session(
        bot=bot,
        chat_id=chat_id,
        project=project,
        name=branch_name,
        create_worktree=True,
        base_branch=base_branch,
    )

    return thread
