"""Branch/worktree operations."""
import subprocess
from pathlib import Path

from aiogram import Bot

from ..session_manager import project_manager, ProjectState, ThreadInfo
from ..logging_config import logger


async def archive_thread(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    thread: ThreadInfo,
) -> None:
    """Archive thread: kill tmux, close topic, keep worktree for resume.

    Used by /finish command. Does NOT delete worktree or git branch.

    Args:
        bot: Telegram bot instance
        chat_id: Chat ID for the topic
        project: Project state
        thread: Thread to archive
    """
    # Cancel all background tasks
    for task in [thread.launch_task, thread.watcher_task, thread.poller_task, thread.binding_task]:
        if task and not task.done():
            task.cancel()

    # Kill tmux
    tmux_name = thread.get_tmux_session(project.project_name)
    subprocess.run(["tmux", "kill-session", "-t", tmux_name], capture_output=True)

    # Archive topic in Telegram
    try:
        await bot.close_forum_topic(chat_id, thread.thread_id)
        logger.info(f"Topic {thread.thread_id} closed")
    except Exception as e:
        logger.debug(f"close_forum_topic failed (may be already closed): {e}")

    try:
        await bot.edit_forum_topic(chat_id, thread.thread_id, icon_custom_emoji_id="5357315181649076022")  # 📁
        logger.info(f"Topic {thread.thread_id} icon set to 📁")
    except Exception as e:
        logger.warning(f"Failed to set archive icon: {e}")

    # Update thread state (keep worktree_path and session_id for resume!)
    thread.archived = True
    thread.notified_closed = True  # Prevent duplicate "session closed" from history_watcher
    project_manager._save()


async def do_branch_create(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    branch_name: str,
    base_branch: str,
):
    """Create topic + worktree + launch Claude.

    Returns:
        CreateThreadResult with success/thread or error
    """
    from .launch import create_thread_with_session

    return await create_thread_with_session(
        bot=bot,
        chat_id=chat_id,
        project=project,
        name=branch_name,
        create_worktree=True,
        base_branch=base_branch,
    )


def create_worktree(project_cwd: Path, branch_name: str) -> tuple[bool, str]:
    """Create worktree for existing branch.

    Returns (success, path_or_error).
    """
    worktree_path = project_cwd / ".worktrees" / branch_name

    try:
        # Prune stale worktrees first (handles "missing but registered" case)
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=project_cwd,
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            cwd=project_cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, str(worktree_path)
    except Exception as e:
        return False, str(e)


def create_branch_with_worktree(project_cwd: Path, branch_name: str) -> tuple[bool, str]:
    """Create new branch and worktree.

    Returns (success, path_or_error).
    """
    worktree_path = project_cwd / ".worktrees" / branch_name

    try:
        # Prune stale worktrees first (handles "missing but registered" case)
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=project_cwd,
            capture_output=True,
        )

        # Create worktree with new branch
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            cwd=project_cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, str(worktree_path)
    except Exception as e:
        return False, str(e)
