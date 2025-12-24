# src/telegram_bridge/main.py
import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher

from .config import settings
from .bot import router, get_session
from .watcher import watch_jsonl, ContentType
from .chunker import chunk_message
from .screen import parse_screen, PermissionPrompt, ToolProgress
from .keyboards import permission_keyboard

# Separators for Telegram display (adjustable length)
SEPARATOR_SOLID = "─" * 20
SEPARATOR_DASHED = "╌" * 20

# Track permission messages for deletion: {keyboard_msg_id: [content_msg_ids]}
permission_messages: dict[int, list[int]] = {}


def format_permission_content(perm: PermissionPrompt) -> str:
    """Format permission prompt content for Telegram display."""
    parts = []

    if perm.description:
        parts.append(SEPARATOR_SOLID)
        parts.append(perm.description)

    if perm.content:
        parts.append(SEPARATOR_DASHED)
        parts.append(perm.content)
        parts.append(SEPARATOR_DASHED)

    if perm.question:
        parts.append(perm.question)

    return "\n".join(parts)


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
                        await bot.send_message(settings.chat_id, f"● {chunk}", parse_mode="Markdown")
                    except Exception:
                        # Fallback if markdown breaks
                        await bot.send_message(settings.chat_id, f"● {chunk}")

            elif entry.content_type == ContentType.TOOL_USE:
                # Send tool info
                tool_info = format_tool_use(entry.tool_name, entry.tool_input)
                try:
                    msg = await bot.send_message(settings.chat_id, tool_info, parse_mode="Markdown")
                except Exception:
                    msg = await bot.send_message(settings.chat_id, tool_info)

                # Start polling for permission/progress
                s = get_session()
                last_state = None
                permission_msg = None  # Track message with keyboard

                while True:
                    await asyncio.sleep(0.5)

                    screen = s.capture_pane()
                    state = parse_screen(screen)

                    if isinstance(state, PermissionPrompt):
                        if last_state != state.options:
                            kb = permission_keyboard(state.options)
                            if permission_msg:
                                await permission_msg.edit_reply_markup(reply_markup=kb)
                            else:
                                # Edit the tool message to add keyboard
                                await msg.edit_reply_markup(reply_markup=kb)
                                permission_msg = msg
                            last_state = state.options

                    elif isinstance(state, ToolProgress):
                        # Could update message with progress here
                        pass

                    else:
                        # Idle - permission was handled or tool finished
                        if permission_msg:
                            # Remove keyboard if still there
                            try:
                                await permission_msg.edit_reply_markup(reply_markup=None)
                            except Exception:
                                pass
                        break

        except Exception as e:
            # Fallback without markdown
            if entry.content_type == ContentType.TEXT:
                await bot.send_message(settings.chat_id, f"● {entry.text[:4000]}")
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
