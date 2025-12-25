# src/telegram_bridge/main.py
import asyncio
from pathlib import Path
from aiohttp import web
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router
from .session_manager import project_manager, ProjectState
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

    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project)

    async def start_watcher(project: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project)

    project = await project_manager.update_from_hook(
        session_id=session_id,
        cwd=cwd,
        tmux_session=tmux_session or "unknown",
        start_poller=start_poller,
        start_watcher=start_watcher,
    )

    return web.json_response({
        "status": "registered",
        "project": project.project_name,
        "has_chat": project.chat_id is not None,
    })

async def handle_unregister(request: web.Request) -> web.Response:
    """Handle session unregistration from Claude hook."""
    data = await request.json()
    session_id = data.get("session_id")

    if not session_id:
        return web.json_response({"error": "missing session_id"}, status=400)

    await project_manager.handle_session_end(session_id)
    return web.json_response({"status": "unregistered"})

async def handle_debug(request: web.Request) -> web.Response:
    """Debug endpoint to inspect bot state."""
    projects_info = {}
    for name, p in project_manager.projects.items():
        projects_info[name] = {
            "chat_id": p.chat_id,
            "tmux": p.tmux_session,
            "claude_session": p.claude_session_id,
            "jsonl_path": p.jsonl_path,
            "cwd": p.cwd,
            "poller_running": p.poller_task is not None and not p.poller_task.done(),
            "watcher_running": p.watcher_task is not None and not p.watcher_task.done(),
        }
    return web.json_response({
        "projects": projects_info,
        "project_count": len(project_manager.projects),
    })

async def run_http_server(bot: Bot) -> None:
    """Run HTTP server for session registration."""
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/session/register", handle_register)
    app.router.add_post("/session/unregister", handle_unregister)
    app.router.add_get("/debug", handle_debug)

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
        BotCommand(command="start", description="Start Claude / show status"),
        BotCommand(command="restart_session", description="Restart Claude session"),
        BotCommand(command="my_chat_id", description="Show your user ID"),
        BotCommand(command="esc", description="Send Escape to Claude"),
    ])

    # Start HTTP server
    await run_http_server(bot)

    # Restore sessions
    async def start_poller(project: ProjectState) -> asyncio.Task:
        from .permission_poller import create_poller_task
        return await create_poller_task(bot, project)

    async def start_watcher(project: ProjectState) -> asyncio.Task:
        from .watcher import create_watcher_task
        return await create_watcher_task(bot, project)

    await project_manager.restore_projects(start_poller, start_watcher)

    # Start Telegram polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
