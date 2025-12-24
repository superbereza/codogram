# src/telegram_bridge/main.py
import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router, get_session
from .watcher import watch_jsonl, ContentType
from .chunker import chunk_message

def find_jsonl_path() -> Path | None:
    """Find latest jsonl for project."""
    # Claude uses path with leading dash: /home/user/project -> -home-user-project
    project_hash = settings.project_dir.replace("/", "-")
    projects_dir = Path.home() / ".claude" / "projects" / project_hash
    if not projects_dir.exists():
        return None
    jsonl_files = sorted(projects_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    return jsonl_files[-1] if jsonl_files else None

async def watcher_task(bot: Bot):
    """Watch jsonl and send updates to Telegram."""
    print("Watcher: waiting for jsonl...")

    while True:
        path = find_jsonl_path()
        if path:
            print(f"Watcher: found {path}")
            break
        await asyncio.sleep(2)

    async for entry in watch_jsonl(path):
        if entry.content_type == ContentType.TEXT:
            symbol = "✓" if entry.is_complete else "◐"
            for chunk in chunk_message(entry.text):
                await bot.send_message(settings.chat_id, f"{symbol} {chunk}")
        elif entry.content_type == ContentType.TOOL_USE:
            await bot.send_message(settings.chat_id, f"◐ {entry.tool_name}")

async def main():
    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Starting bridge for chat {settings.chat_id}")
    print(f"Project: {settings.project_dir}")

    asyncio.create_task(watcher_task(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
