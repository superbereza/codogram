# src/telegram_bridge/main.py
import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router, get_session
from .watcher import watch_jsonl, ContentType
from .chunker import chunk_message


def format_tool_use(tool_name: str, tool_input: dict | None) -> str:
    """Format tool use for Telegram display. Uses ● for permission requests."""
    if not tool_input:
        return f"● *{tool_name}*"

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")[:500]
        desc = tool_input.get("description", "")
        if desc:
            return f"● *Bash*: {desc}\n`{cmd}`"
        return f"● *Bash*\n`{cmd}`"

    elif tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"● *Read* `{path}`"

    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        return f"● *Write* `{path}`"

    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return f"● *Edit* `{path}`"

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"● *Glob* `{pattern}`"

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"● *Grep* `{pattern}`"

    elif tool_name == "Task":
        desc = tool_input.get("description", "")
        return f"● *Task*: {desc}"

    elif tool_name == "TodoWrite":
        return f"● *TodoWrite*"

    else:
        # Generic fallback
        preview = str(tool_input)[:200]
        return f"● *{tool_name}*\n`{preview}`"

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
        try:
            if entry.content_type == ContentType.TEXT:
                # Send each text as new message (no streaming)
                for chunk in chunk_message(entry.text):
                    try:
                        await bot.send_message(settings.chat_id, f"• {chunk}", parse_mode="Markdown")
                    except Exception:
                        # Fallback if markdown breaks
                        await bot.send_message(settings.chat_id, f"• {chunk}")

            elif entry.content_type == ContentType.TOOL_USE:
                tool_info = format_tool_use(entry.tool_name, entry.tool_input)
                await bot.send_message(settings.chat_id, tool_info, parse_mode="Markdown")

        except Exception as e:
            # Fallback without markdown
            if entry.content_type == ContentType.TEXT:
                await bot.send_message(settings.chat_id, f"• {entry.text[:4000]}")
            elif entry.content_type == ContentType.TOOL_USE:
                await bot.send_message(settings.chat_id, f"● {entry.tool_name}")

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
