# src/telegram_bridge/watcher.py
import json
import asyncio
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

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
