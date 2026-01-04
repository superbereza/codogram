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
from .handlers import register_handlers
from .session_manager import project_manager, ProjectState
from .tmux import TmuxSession
from .logging_config import setup_logging, logger
from .telegram_queue import TelegramQueue

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

    # Global admin check - protects ALL routers
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())

    # Register handler routers (all protected by AdminMiddleware)
    register_handlers(dp)

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Start Claude / show status"),
        BotCommand(command="new", description="Start new Claude session (/clear)"),
        # /clear intentionally not in menu - same as /new
        BotCommand(command="thread_create", description="Create new Claude thread"),
        BotCommand(command="thread_delete", description="Delete Claude thread (in topic)"),
        BotCommand(command="branch_create", description="Create isolated git worktree + thread"),
        BotCommand(command="branch_finish", description="Merge branch and cleanup worktree"),
        BotCommand(command="restart", description="Kill and restart Claude tmux"),
        BotCommand(command="settings", description="Show current settings"),
        BotCommand(command="auto_accept", description="Toggle auto-accept (or reset all)"),
        BotCommand(command="help", description="Show available commands"),
        BotCommand(command="get_debug_ids", description="Show debug IDs (admin only)"),
        BotCommand(command="esc", description="Send Escape to Claude"),
        # /resume intentionally not in menu - just responds "not supported" if someone tries it
    ])

    # Define task starters
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project, telegram_queue)

    async def start_watcher(project: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project, telegram_queue, send_missed)

    # Restore sessions from history.jsonl
    await project_manager.restore_projects(bot, start_poller, start_watcher, telegram_queue)

    # Start history watcher for session changes
    from .history_watcher import create_history_watcher
    await create_history_watcher(bot, start_poller, start_watcher, telegram_queue)

    logger.info("History watcher started (15s polling)")

    # Start Telegram polling
    try:
        await dp.start_polling(bot)
    finally:
        if telegram_queue:
            await telegram_queue.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
