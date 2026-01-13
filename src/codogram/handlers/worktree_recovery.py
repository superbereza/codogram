# src/codogram/handlers/worktree_recovery.py
"""Worktree recovery callbacks for stale worktree handling."""
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from codogram.services.branch import archive_thread, create_worktree, create_branch_with_worktree
from codogram.session_manager import ProjectManager
from codogram.telegram_queue import TelegramQueue


class WorktreeRecoveryHandler:
    """Handle worktree recovery callbacks."""

    def __init__(self, project_manager: ProjectManager, queue: TelegramQueue, bot: Bot):
        self.project_manager = project_manager
        self.queue = queue
        self.bot = bot

    async def handle_wr_recreate(self, callback: CallbackQuery) -> None:
        """Recreate worktree from existing branch."""
        await callback.answer()
        thread_id = int(callback.data.split(":")[1])
        thread = self.project_manager.get_thread(thread_id)

        if not thread:
            await callback.message.edit_text("`[x]` Thread not found")
            return

        project = self.project_manager.get_project()
        success, path = create_worktree(Path(project.cwd), thread.name)

        if success:
            thread.worktree_path = path
            self.project_manager.save()
            await callback.message.delete()
            await self._start_claude_session(callback.message, thread)
        else:
            await callback.message.edit_text(
                f"`[x]` Failed to recreate worktree: {path}\n\n"
                "What to do:\n"
                "* /finish \u2014 archive this topic\n"
                "* /thread \u2014 create new topic in main\n"
                "* /branch \u2014 create new worktree branch"
            )

    async def handle_wr_create(self, callback: CallbackQuery) -> None:
        """Create new branch and worktree."""
        await callback.answer()
        thread_id = int(callback.data.split(":")[1])
        thread = self.project_manager.get_thread(thread_id)

        if not thread:
            await callback.message.edit_text("`[x]` Thread not found")
            return

        project = self.project_manager.get_project()
        success, path = create_branch_with_worktree(Path(project.cwd), thread.name)

        if success:
            thread.worktree_path = path
            self.project_manager.save()
            await callback.message.delete()
            await self._start_claude_session(callback.message, thread)
        else:
            await callback.message.edit_text(
                f"`[x]` Failed to create branch: {path}\n\n"
                "What to do:\n"
                "* /finish \u2014 archive this topic\n"
                "* /thread \u2014 create new topic in main\n"
                "* /branch \u2014 create new worktree branch"
            )

    async def handle_wr_main(self, callback: CallbackQuery) -> None:
        """Resume in main by archiving topic."""
        await callback.answer()
        thread_id = int(callback.data.split(":")[1])
        thread = self.project_manager.get_thread(thread_id)

        if not thread:
            await callback.message.edit_text("`[x]` Thread not found")
            return

        project = self.project_manager.get_project()
        await archive_thread(self.bot, callback.message.chat.id, project, thread)
        await callback.message.edit_text(
            "`[v]` Topic archived\n\n"
            "Use General or /thread for new session."
        )

    async def handle_wr_cancel(self, callback: CallbackQuery) -> None:
        """Cancel recovery - just delete message."""
        await callback.answer()
        await callback.message.delete()

    async def _start_claude_session(self, message, thread) -> None:
        """Start Claude session in recovered worktree.

        Note: This delegates to StartHandler._start_claude_session.
        Implemented during integration.
        """
        # Will be connected during router setup
        pass


def register_worktree_recovery_handlers(router: Router, handler: WorktreeRecoveryHandler) -> None:
    """Register worktree recovery callback handlers."""
    router.callback_query.register(handler.handle_wr_recreate, F.data.startswith("wr_recreate:"))
    router.callback_query.register(handler.handle_wr_create, F.data.startswith("wr_create:"))
    router.callback_query.register(handler.handle_wr_main, F.data.startswith("wr_main:"))
    router.callback_query.register(handler.handle_wr_cancel, F.data.startswith("wr_cancel:"))
