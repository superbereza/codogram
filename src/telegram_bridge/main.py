# src/telegram_bridge/main.py
import asyncio
from pathlib import Path
from aiohttp import web
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router
from .session_manager import manager, SessionState
from .tmux import TmuxSession

# HTTP handlers
async def handle_register(request: web.Request) -> web.Response:
    """Handle session registration from Claude hook."""
    data = await request.json()
    session_id = data.get("session_id")
    cwd = data.get("cwd")
    tmux_session = data.get("tmux_session")

    if not session_id or not cwd:
        return web.json_response({"error": "missing fields"}, status=400)

    bot = request.app["bot"]

    async def start_poller(session: SessionState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return asyncio.create_task(create_poller_task(bot, session))

    async def start_watcher(session: SessionState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return asyncio.create_task(create_watcher_task(bot, session))

    session = await manager.register_session(
        session_id=session_id,
        cwd=cwd,
        tmux_session=tmux_session or "unknown",
        start_poller=start_poller,
        start_watcher=start_watcher,
    )

    return web.json_response({
        "status": "registered",
        "project": session.project_name,
        "has_chat": session.chat_id is not None,
    })

async def handle_unregister(request: web.Request) -> web.Response:
    """Handle session unregistration from Claude hook."""
    data = await request.json()
    session_id = data.get("session_id")

    if not session_id:
        return web.json_response({"error": "missing session_id"}, status=400)

    await manager.unregister_session(session_id)
    return web.json_response({"status": "unregistered"})

async def run_http_server(bot: Bot) -> None:
    """Run HTTP server for session registration."""
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/session/register", handle_register)
    app.router.add_post("/session/unregister", handle_unregister)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", settings.http_port)
    await site.start()
    print(f"HTTP server running on http://localhost:{settings.http_port}")

async def main():
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Starting bridge")
    print(f"Admin IDs: {settings.get_admin_ids()}")
    print(f"Base dir: {settings.base_dir}")

    # Register bot commands menu
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot / show status"),
        BotCommand(command="my_chat_id", description="Show your user ID"),
        BotCommand(command="register_dir", description="Register project for this chat"),
        BotCommand(command="esc", description="Send Escape to Claude"),
    ])

    # Start HTTP server
    await run_http_server(bot)

    # Restore sessions from config
    async def start_poller(session: SessionState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return asyncio.create_task(create_poller_task(bot, session))

    async def start_watcher(session: SessionState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return asyncio.create_task(create_watcher_task(bot, session))

    await manager.restore_sessions(start_poller, start_watcher)

    # Start Telegram polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
