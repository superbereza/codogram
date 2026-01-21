# src/codogram/handlers/worktree_recovery.py
"""Worktree recovery callbacks for stale worktree handling."""
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from codogram import strings
from codogram.services.branch import archive_thread, create_worktree, create_branch_with_worktree
from codogram.session_manager import ProjectManager
from codogram.telegram.queue import TelegramQueue

logger = logging.getLogger(__name__)


def _parse_thread_id(callback_data: str) -> int | None:
    """Parse thread_id from callback data like 'wr_recreate:123'."""
    try:
        return int(callback_data.split(":")[1])
    except (IndexError, ValueError):
        return None


class WorktreeRecoveryHandler:
    """Handle worktree recovery callbacks."""

    def __init__(self, project_manager: ProjectManager, queue: TelegramQueue, bot: Bot):
        self.project_manager = project_manager
        self.queue = queue
        self.bot = bot

    async def handle_wr_recreate(self, callback: CallbackQuery) -> None:
        """Recreate worktree from existing branch."""
        await callback.answer()
        thread_id = _parse_thread_id(callback.data)
        if thread_id is None:
            logger.warning("Malformed callback data: %s", callback.data)
            await self.queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
            return

        project = self.project_manager.get_by_chat(callback.message.chat.id)
        if not project:
            await self.queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
            return

        thread = project.get_thread(thread_id)
        if not thread:
            await self.queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
            return
        success, path = create_worktree(Path(project.cwd), thread.name)

        if success:
            thread.worktree_path = path
            self.project_manager._save()
            await callback.message.delete()
            await self._start_claude_session(callback.message, thread)
        else:
            await self.queue.edit(
                callback.message, strings.WORKTREE_RECREATE_FAILED.format(path=path)
            )

    async def handle_wr_create(self, callback: CallbackQuery) -> None:
        """Create new branch and worktree."""
        await callback.answer()
        thread_id = _parse_thread_id(callback.data)
        if thread_id is None:
            logger.warning("Malformed callback data: %s", callback.data)
            await self.queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
            return

        project = self.project_manager.get_by_chat(callback.message.chat.id)
        if not project:
            await self.queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
            return

        thread = project.get_thread(thread_id)
        if not thread:
            await self.queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
            return
        success, path = create_branch_with_worktree(Path(project.cwd), thread.name)

        if success:
            thread.worktree_path = path
            self.project_manager._save()
            await callback.message.delete()
            await self._start_claude_session(callback.message, thread)
        else:
            await self.queue.edit(
                callback.message, strings.WORKTREE_BRANCH_CREATE_FAILED.format(path=path)
            )

    async def handle_wr_main(self, callback: CallbackQuery) -> None:
        """Resume in main by archiving topic."""
        await callback.answer()
        thread_id = _parse_thread_id(callback.data)
        if thread_id is None:
            logger.warning("Malformed callback data: %s", callback.data)
            await self.queue.edit(callback.message, strings.ERR_INVALID_CALLBACK)
            return

        project = self.project_manager.get_by_chat(callback.message.chat.id)
        if not project:
            await self.queue.edit(callback.message, strings.ERR_PROJECT_NOT_FOUND)
            return

        thread = project.get_thread(thread_id)
        if not thread:
            await self.queue.edit(callback.message, strings.ERR_THREAD_NOT_FOUND)
            return
        await archive_thread(self.bot, callback.message.chat.id, project, thread)
        await self.queue.edit(callback.message, strings.WORKTREE_TOPIC_ARCHIVED)

    async def handle_wr_cancel(self, callback: CallbackQuery) -> None:
        """Cancel recovery - just delete message."""
        await callback.answer()
        await callback.message.delete()

    async def _start_claude_session(self, message, thread) -> None:
        """Start Claude session in recovered worktree."""
        import asyncio
        from ..telegram.launch_animation import launch_with_animation

        project = self.project_manager.get_by_chat(message.chat.id)
        if not project:
            return

        cwd = thread.worktree_path if thread and thread.worktree_path else None

        thread.launch_task = asyncio.create_task(
            launch_with_animation(
                bot=self.bot,
                chat_id=message.chat.id,
                thread_id=thread.thread_id,
                project=project,
                thread=thread,
                queue=self.queue,
                cwd=cwd,
            )
        )


def register_worktree_recovery_handlers(router: Router, handler: WorktreeRecoveryHandler) -> None:
    """Register worktree recovery callback handlers."""
    router.callback_query.register(handler.handle_wr_recreate, F.data.startswith("wr_recreate:"))
    router.callback_query.register(handler.handle_wr_create, F.data.startswith("wr_create:"))
    router.callback_query.register(handler.handle_wr_main, F.data.startswith("wr_main:"))
    router.callback_query.register(handler.handle_wr_cancel, F.data.startswith("wr_cancel:"))
