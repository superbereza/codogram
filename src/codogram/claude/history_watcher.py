# src/codogram/claude/history_watcher.py
import json
import asyncio
import re
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from ..telegram.queue import TelegramQueue
from aiogram import Bot
from ..config import settings, get_global_defaults
from ..core.session_manager import get_thread_setting
from ..logging_config import logger
from .. import strings
from .tool_formatter import format_tool_use


def _process_thinking_text(text: str, display_thinking_text: bool) -> str:
    """Process <thinking> blocks in text response.

    Args:
        text: Claude's text response
        display_thinking_text: If True, show as italic. If False, replace with summary.

    Returns:
        Processed text
    """
    pattern = r'<thinking>(.*?)</thinking>'

    if display_thinking_text:
        # Show tags on separate lines, content as italic
        def italicize(match):
            content = match.group(1).strip()
            return f"<thinking>\n_{content}_\n</thinking>"
        return re.sub(pattern, italicize, text, flags=re.DOTALL)
    else:
        # Replace with summary
        def summarize(match):
            content = match.group(1)
            length = len(content)
            return f"thinking • {length} symbols"
        return re.sub(pattern, summarize, text, flags=re.DOTALL)


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
                content = str(item.get("content", ""))
                if len(content) > 500:
                    content = content[:500] + f"\n{strings.SNIP}"
                return ParsedEntry(
                    content_type=ContentType.TOOL_RESULT,
                    text=content
                )
        return None

    # Handle assistant entries
    if entry_type != "assistant":
        return None

    message = entry.get("message", {})

    # Skip "No response requested." synthetic messages (from hooks)
    # But keep API errors - those are useful to show
    if message.get("model") == "<synthetic>":
        content = message.get("content", [])
        if content and content[0].get("text") == "No response requested.":
            return None
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
            thinking = item.get("thinking", "")
            if len(thinking) > 100:
                thinking = thinking[:100] + f" {strings.SNIP}"
            return ParsedEntry(
                content_type=ContentType.THINKING,
                text=thinking
            )

    return None

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
    from ..core.session_manager import ProjectState

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
        watch_thread_jsonl(bot, project, main_thread, telegram_queue)
    )


async def watch_thread_jsonl(bot: Bot, project, thread, telegram_queue: "TelegramQueue"):
    """Watch jsonl for a thread and send entries through queue.

    Supports all display modes including 'current' mode which edits
    a single message instead of sending multiple.
    """
    from ..telegram.queue import OutgoingBatch, EditBatch
    from pathlib import Path

    if not thread.jsonl_path:
        logger.warning(f"watch_thread_jsonl: no jsonl_path for thread={thread.name}")
        return

    logger.info(f"thread_watcher_started: thread={thread.name}, session={thread.session_id[:8] if thread.session_id else 'None'}")
    watcher = JsonlWatcher(Path(thread.jsonl_path))

    # State for "current" mode - tracks whether we've sent the first tool message
    current_mode_key = f"current:{project.chat_id}:{thread.thread_id}"
    current_mode_active = False  # True after first tool message sent in "current" mode

    try:
        async for entry in watcher.watch():
            try:
                # Get display settings from thread (with fallback to global defaults)
                global_defaults = get_global_defaults()
                display_mode = get_thread_setting(thread, 'display_mode', global_defaults)
                line_limit = get_thread_setting(thread, 'line_limit', global_defaults)
                display_bullet = get_thread_setting(thread, 'display_bullet', global_defaults)
                display_thinking_text = get_thread_setting(thread, 'display_thinking_text', global_defaults)

                messages = _entry_to_messages(
                    entry,
                    display_mode=display_mode,
                    line_limit=line_limit,
                    display_bullet=display_bullet,
                    display_thinking_text=display_thinking_text,
                )

                if not messages:
                    continue

                # Logging
                text_preview = messages[0].get("text", "")[:40].replace("\n", " ")
                msg_id = hash(text_preview) & 0xFFFFFF
                logger.info(f"message_read: msg_id={msg_id:06x} thread={thread.name} preview='{text_preview}'")

                if display_mode == "current" and entry.content_type == ContentType.TOOL_USE:
                    # In "current" mode, edit single message for tool calls
                    text = messages[0]["text"]
                    parse_mode = messages[0].get("parse_mode")
                    logger.debug(f"watcher: current mode, active={current_mode_active}")

                    if not current_mode_active:
                        # First tool - send new message with replace_key
                        batch = OutgoingBatch(
                            chat_id=project.chat_id,
                            thread_id=thread.thread_id,
                            messages=messages,
                            replace_key=current_mode_key,
                        )
                        telegram_ids = await telegram_queue.enqueue(batch)
                        logger.info(f"message_sent: msg_id={msg_id:06x} thread={thread.name} telegram_ids={telegram_ids}")
                        current_mode_active = True
                    else:
                        # Subsequent tools - edit existing message
                        batch = EditBatch(
                            chat_id=project.chat_id,
                            message_id=0,  # Lookup from sent_statuses using replace_key
                            text=text,
                            parse_mode=parse_mode,
                            replace_key=current_mode_key,
                        )
                        await telegram_queue.enqueue(batch)
                        logger.info(f"message_edited: msg_id={msg_id:06x} thread={thread.name}")
                else:
                    # Normal mode or non-tool content - send as usual
                    batch = OutgoingBatch(
                        chat_id=project.chat_id,
                        thread_id=thread.thread_id,
                        messages=messages,
                    )
                    telegram_ids = await telegram_queue.enqueue(batch)
                    logger.info(f"message_sent: msg_id={msg_id:06x} thread={thread.name} telegram_ids={telegram_ids}")

                    # Reset current mode state on TEXT content (Claude's response)
                    # This starts fresh for the next sequence of tool calls
                    if entry.content_type == ContentType.TEXT:
                        current_mode_active = False

                # Signal poller to resend thinking status (so it appears at bottom)
                thread.thinking_needs_resend = True

            except Exception as e:
                logger.error(f"watch_thread_error: {e}")
    except asyncio.CancelledError:
        logger.info(f"watch_thread_cancelled: thread={thread.name}")
        raise


def _entry_to_messages(
    entry: ParsedEntry,
    display_mode: str = "lines",
    line_limit: int = 5,
    display_bullet: bool = True,
    display_thinking_text: bool = True,
) -> list[dict]:
    """Convert ParsedEntry to list of message dicts for queue."""
    messages = []

    if entry.content_type == ContentType.TEXT:
        bullet = "● " if display_bullet else ""
        text = entry.text

        # Process thinking blocks
        text = _process_thinking_text(text, display_thinking_text)

        messages.append({"text": f"{bullet}{text}", "parse_mode": "MarkdownV2"})

    elif entry.content_type == ContentType.TOOL_USE:
        # Hide AskUserQuestion - shown by poller instead
        if entry.tool_name == "AskUserQuestion":
            return []

        text = format_tool_use(
            entry.tool_name,
            entry.tool_input,
            display_mode=display_mode,
            line_limit=line_limit,
            display_bullet=display_bullet,
        )
        if text:  # None in silence mode
            messages.append({"text": text, "parse_mode": "MarkdownV2"})

    return messages
