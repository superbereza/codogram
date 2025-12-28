# src/codogram/main.py
import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router
from .session_manager import project_manager, ProjectState
from .tmux import TmuxSession
from .logging_config import setup_logging, logger

async def main():
    setup_logging()
    logger.info("Starting Telegram Bridge (history.jsonl mode)")
    logger.info(f"Admin IDs: {settings.get_admin_ids()}")
    logger.info(f"Base dir: {settings.base_dir}")

    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Start Claude / show status"),
        BotCommand(command="session_new", description="Create new Claude thread"),
        BotCommand(command="session_close", description="Close Claude thread (use in topic)"),
        BotCommand(command="restart_session", description="Restart Claude session"),
        BotCommand(command="my_chat_id", description="Show your user ID"),
        BotCommand(command="esc", description="Send Escape to Claude"),
        # /resume intentionally not in menu - just responds "not supported" if someone tries it
    ])

    # Define task starters
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project)

    async def start_watcher(project: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project, send_missed)

    # Restore sessions from history.jsonl
    await project_manager.restore_projects(bot, start_poller, start_watcher)

    # Start history watcher for session changes
    from .history_watcher import create_history_watcher
    await create_history_watcher(bot, start_poller, start_watcher)

    logger.info("History watcher started (15s polling)")

    # Start Telegram polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
