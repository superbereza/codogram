# src/codogram/watcher.py
import json
import asyncio
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from .telegram_queue import TelegramQueue
from aiogram import Bot
from .config import settings
from .logging_config import logger

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
        return f"● **{tool_name}**"

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")[:500]
        desc = tool_input.get("description", "")
        if desc:
            return f"● **Bash**: {desc}\n`{cmd}`"
        return f"● **Bash**\n`{cmd}`"
    elif tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"● **Read** `{path}`"
    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        return f"● **Write** `{path}`"
    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return f"● **Edit** `{path}`"
    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"● **Glob** `{pattern}`"
    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"● **Grep** `{pattern}`"
    elif tool_name == "Task":
        desc = tool_input.get("description", "")
        return f"● **Task**: {desc}"
    elif tool_name == "TodoWrite":
        return f"● **TodoWrite**"
    else:
        preview = str(tool_input)[:200]
        return f"● **{tool_name}**\n`{preview}`"

class JsonlWatcher:
    """Watches a jsonl file and yields new entries."""

    def __init__(self, path: Path, poll_interval: float | None = None):
        self.path = path
        self.poll_interval = poll_interval if poll_interval is not None else settings.jsonl_watcher_interval
        self.last_position = path.stat().st_size if path.exists() else 0

    async def watch(self) -> AsyncIterator[ParsedEntry]:
        """Watch jsonl file and yield new parsed entries."""
        while True:
            try:
                current_size = self.path.stat().st_size
            except FileNotFoundError:
                await asyncio.sleep(self.poll_interval)
                continue

            if current_size > self.last_position:
                with open(self.path, "r") as f:
                    f.seek(self.last_position)
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
                    self.last_position = f.tell()

            await asyncio.sleep(self.poll_interval)


async def watch_jsonl(path: Path, poll_interval: float | None = None) -> AsyncIterator[ParsedEntry]:
    """Watch jsonl file and yield new parsed entries."""
    watcher = JsonlWatcher(path, poll_interval)
    async for entry in watcher.watch():
        yield entry


async def create_watcher_task(
    bot: Bot,
    project,
    telegram_queue: "TelegramQueue",
    send_missed: bool = False,
) -> asyncio.Task:
    """Create jsonl watcher task for project's main thread.

    This is a compatibility shim - actual watching is done per-thread
    via watch_thread_jsonl in history_watcher.py.
    """
    from .session_manager import ProjectState

    if not isinstance(project, ProjectState):
        raise TypeError("project must be ProjectState")

    # Get or create main thread
    main_thread = project.get_or_create_thread(None, "main")

    if not main_thread.jsonl_path:
        # No session yet, return a no-op task
        async def noop():
            pass
        return asyncio.create_task(noop())

    # Create watcher for main thread
    return asyncio.create_task(
        _watch_with_queue(bot, project, main_thread, telegram_queue)
    )


async def _watch_with_queue(bot: Bot, project, thread, telegram_queue: "TelegramQueue"):
    """Watch jsonl and send entries through queue."""
    from .telegram_queue import OutgoingBatch
    from pathlib import Path

    if not thread.jsonl_path:
        return

    watcher = JsonlWatcher(Path(thread.jsonl_path))

    try:
        async for entry in watcher.watch():
            try:
                messages = _entry_to_messages(entry)
                if messages:
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    await telegram_queue.enqueue_nowait(batch)
            except Exception as e:
                logger.warning(f"watch_with_queue error: {e}")
    except asyncio.CancelledError:
        raise


def _entry_to_messages(entry: ParsedEntry) -> list[dict]:
    """Convert ParsedEntry to list of message dicts for queue."""
    messages = []

    if entry.content_type == ContentType.TEXT:
        messages.append({"text": f"● {entry.text}", "parse_mode": "MarkdownV2"})

    elif entry.content_type == ContentType.TOOL_USE:
        text = format_tool_use(entry.tool_name, entry.tool_input)
        messages.append({"text": text, "parse_mode": "MarkdownV2"})

    return messages
