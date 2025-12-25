# src/telegram_bridge/watcher.py
import json
import asyncio
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
from aiogram import Bot
from .session_manager import ProjectState
from .chunker import chunk_message

class ContentType(Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    UNKNOWN = "unknown"

@dataclass
class ParsedEntry:
    content_type: ContentType
    text: str = ""
    tool_name: str = ""
    tool_input: dict | None = None

def parse_jsonl_entry(entry: dict) -> ParsedEntry | None:
    entry_type = entry.get("type")

    # Tool results come in "user" entries
    if entry_type == "user":
        message = entry.get("message", {})
        content = message.get("content", [])
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_result":
                return ParsedEntry(
                    content_type=ContentType.TOOL_RESULT,
                    text=str(item.get("content", ""))[:500]
                )
        return None

    # Handle assistant entries
    if entry_type != "assistant":
        return None

    message = entry.get("message", {})
    content = message.get("content", [])

    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")

        if item_type == "text":
            return ParsedEntry(
                content_type=ContentType.TEXT,
                text=item.get("text", "")
            )
        elif item_type == "tool_use":
            return ParsedEntry(
                content_type=ContentType.TOOL_USE,
                tool_name=item.get("name", ""),
                tool_input=item.get("input")
            )
        elif item_type == "thinking":
            return ParsedEntry(
                content_type=ContentType.THINKING,
                text=item.get("thinking", "")[:100] + "..."
            )

    return None

def format_tool_use(tool_name: str, tool_input: dict | None) -> str:
    """Format tool use for Telegram display."""
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
        preview = str(tool_input)[:200]
        return f"● *{tool_name}*\n`{preview}`"

async def watch_jsonl(path: Path, poll_interval: float = 0.5) -> AsyncIterator[ParsedEntry]:
    """Watch jsonl file and yield new parsed entries."""
    last_position = path.stat().st_size if path.exists() else 0

    while True:
        if not path.exists():
            await asyncio.sleep(poll_interval)
            continue

        current_size = path.stat().st_size
        if current_size > last_position:
            with open(path, "r") as f:
                f.seek(last_position)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        parsed = parse_jsonl_entry(entry)
                        if parsed:
                            yield parsed
                    except json.JSONDecodeError:
                        pass
                last_position = f.tell()

        await asyncio.sleep(poll_interval)

async def create_watcher_task(bot: Bot, project: ProjectState) -> asyncio.Task:
    """Create watcher task for project."""
    return asyncio.create_task(watcher_for_session(bot, project))

async def watcher_for_session(bot: Bot, project: ProjectState):
    """Watch jsonl for specific project."""
    if not project.jsonl_path:
        print(f"Watcher: no jsonl_path for project {project.session_id[:8]}")
        return

    path = Path(project.jsonl_path)
    chat_id = project.chat_id

    print(f"Watcher: watching {path} for chat {chat_id}")

    async for entry in watch_jsonl(path):
        try:
            if entry.content_type == ContentType.TEXT:
                for chunk in chunk_message(entry.text):
                    try:
                        await bot.send_message(chat_id, f"● {chunk}", parse_mode="Markdown")
                    except Exception:
                        await bot.send_message(chat_id, f"● {chunk}")

            elif entry.content_type == ContentType.TOOL_USE:
                print(f"Watcher: TOOL_USE {entry.tool_name}", flush=True)
                text = format_tool_use(entry.tool_name, entry.tool_input)
                try:
                    await bot.send_message(chat_id, text, parse_mode="Markdown")
                    print(f"Watcher: sent {entry.tool_name}", flush=True)
                except Exception as e:
                    print(f"Watcher: error sending {entry.tool_name}: {e}", flush=True)
                    await bot.send_message(chat_id, f"● {entry.tool_name}")

        except Exception as e:
            if entry.content_type == ContentType.TEXT:
                await bot.send_message(chat_id, f"● {entry.text[:4000]}")
            elif entry.content_type == ContentType.TOOL_USE:
                await bot.send_message(chat_id, f"● {entry.tool_name}")
