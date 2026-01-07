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
from .services.menu import BASIC_COMMANDS

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

    # Register handler routers (all protected by AdminMiddleware)
    register_handlers(dp)

    # Set global default menu (for new chats)
    await bot.set_my_commands(BASIC_COMMANDS)

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
