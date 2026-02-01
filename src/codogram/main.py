# src/codogram/main.py
import sys

# Fix module identity: ensure 'codogram.main' and '__main__' are the same object
# This allows other modules to import telegram_queue correctly
if __name__ == '__main__':
    sys.modules['codogram.main'] = sys.modules['__main__']

import asyncio
import subprocess
from pathlib import Path
from aiogram import Bot, Dispatcher


def get_git_revision() -> str:
    """Get current git commit hash and branch."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return f"{commit} ({branch})" if commit else "unknown"
    except Exception:
        return "unknown"

from .config import settings
from .middleware.admin import AdminMiddleware
from .services.group_auth import GroupAuthService
from .middleware.bot_admin_rights import BotAdminRightsMiddleware
from .middleware.clear_create_state import ClearCreateStateMiddleware
from .middleware.setup_blocker import SetupBlockerMiddleware
from .handlers import register_handlers
from .core.session_manager import project_manager, ProjectState
from .tmux.session import TmuxSession
from .logging_config import setup_logging, logger
from .telegram.queue import TelegramQueue
from .services.menu import BASIC_COMMANDS, register_menu_for_chat, register_dm_commands

telegram_queue: TelegramQueue | None = None

async def main():
    setup_logging()
    logger.info("Starting Telegram Bridge (history.jsonl mode)")
    logger.info(f"Git revision: {get_git_revision()}")
    logger.info(f"Admin IDs: {settings.get_admin_ids()}")
    logger.info(f"Base dir: {settings.base_dir}")

    bot = Bot(token=settings.telegram_token)
    global telegram_queue
    telegram_queue = TelegramQueue(bot)
    dp = Dispatcher()
    dp["telegram_queue"] = telegram_queue  # Register for aiogram DI

    # Group authorization service
    group_auth = GroupAuthService()
    dp["group_auth"] = group_auth  # Register for aiogram DI

    # Get bot info for response mode filtering
    bot_info = await bot.get_me()
    from .services.response_mode import ResponseModeService
    response_mode_service = ResponseModeService(
        bot_id=bot_info.id,
        bot_username=bot_info.username,
    )
    dp["response_mode_service"] = response_mode_service

    # Global admin check - protects ALL routers
    dp.message.middleware(AdminMiddleware(group_auth))
    dp.callback_query.middleware(AdminMiddleware(group_auth))

    # Block if bot awaiting admin rights (after migration)
    dp.message.middleware(BotAdminRightsMiddleware())
    dp.callback_query.middleware(BotAdminRightsMiddleware())

    # Clear create flow state when any command is sent
    dp.message.middleware(ClearCreateStateMiddleware())

    # Block non-setup commands during setup flow
    dp.message.middleware(SetupBlockerMiddleware())

    # Register handler routers (all protected by AdminMiddleware)
    register_handlers(dp)

    # Set global default menu (for new chats)
    await bot.set_my_commands(BASIC_COMMANDS)

    # Set commands for private chats (DM)
    await register_dm_commands(bot)

    # Define task starters
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .claude.poller import create_poller_task
        return await create_poller_task(bot, project, telegram_queue)

    async def start_watcher(project: ProjectState, send_missed: bool = False) -> asyncio.Task:
        from .claude.history_watcher import create_watcher_task
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
    from .core.coordinator import create_history_watcher
    await create_history_watcher(bot, start_poller, start_watcher, telegram_queue)

    logger.info("History watcher started (15s polling)")

    # Start Telegram polling
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"])
    finally:
        if telegram_queue:
            await telegram_queue.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
