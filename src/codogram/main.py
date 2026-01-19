# src/codogram/main.py
import sys

# Fix module identity: ensure 'codogram.main' and '__main__' are the same object
# This allows other modules to import telegram_queue correctly
if __name__ == '__main__':
    sys.modules['codogram.main'] = sys.modules['__main__']

import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher

from .config import settings
from .middleware.admin import AdminMiddleware
from .middleware.clear_create_state import ClearCreateStateMiddleware
from .middleware.setup_blocker import SetupBlockerMiddleware
from .handlers import register_handlers
from .session_manager import project_manager, ProjectState
from .tmux import TmuxSession
from .logging_config import setup_logging, logger
from .telegram_queue import TelegramQueue
from .services.menu import BASIC_COMMANDS, register_menu_for_chat, register_dm_commands
from .handlers.worktree_recovery import WorktreeRecoveryHandler, register_worktree_recovery_handlers

telegram_queue: TelegramQueue | None = None

async def main():
    setup_logging()
    logger.info("Starting Telegram Bridge (history.jsonl mode)")
    logger.info(f"Admin IDs: {settings.get_admin_ids()}")
    logger.info(f"Base dir: {settings.base_dir}")

    bot = Bot(token=settings.telegram_token)
    global telegram_queue
    telegram_queue = TelegramQueue(bot)
    dp = Dispatcher()
    dp["telegram_queue"] = telegram_queue  # Register for aiogram DI

    # Global admin check - protects ALL routers
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())

    # Clear create flow state when any command is sent
    dp.message.middleware(ClearCreateStateMiddleware())

    # Block non-setup commands during setup flow
    dp.message.middleware(SetupBlockerMiddleware())

    # Register handler routers (all protected by AdminMiddleware)
    register_handlers(dp)

    # Register worktree recovery handlers (needs bot instance)
    worktree_recovery_handler = WorktreeRecoveryHandler(project_manager, telegram_queue, bot)
    register_worktree_recovery_handlers(dp, worktree_recovery_handler)

    # Set global default menu (for new chats)
    await bot.set_my_commands(BASIC_COMMANDS)

    # Set commands for private chats (DM)
    await register_dm_commands(bot)

    # Define task starters
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project, telegram_queue)

    async def start_watcher(project: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project, telegram_queue, send_missed)

    # Restore sessions from history.jsonl
    await project_manager.restore_projects(bot, start_poller, start_watcher, telegram_queue)

    # Register menus for all known chats (forum chats get extended menu)
    for project in project_manager.projects.values():
        if project.chat_id:
            try:
                chat = await bot.get_chat(project.chat_id)
                await register_menu_for_chat(bot, project.chat_id, is_forum=chat.is_forum or False)
            except Exception as e:
                logger.warning(f"Failed to register menu for {project.project_name}: {e}")

    # Start history watcher for session changes
    from .history_watcher import create_history_watcher
    await create_history_watcher(bot, start_poller, start_watcher, telegram_queue)

    logger.info("History watcher started (15s polling)")

    # Start Telegram polling
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])
    finally:
        if telegram_queue:
            await telegram_queue.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
