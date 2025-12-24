# tests/test_watcher.py
import pytest
import json
import tempfile
from pathlib import Path

from telegram_bridge.watcher import parse_jsonl_entry, ContentType

def test_parse_text_entry():
    entry = {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Hello world"}],
            "stop_reason": "end_turn"
        }
    }
    result = parse_jsonl_entry(entry)
    assert result.content_type == ContentType.TEXT
    assert result.text == "Hello world"

def test_parse_tool_use():
    entry = {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}],
            "stop_reason": "tool_use"
        }
    }
    result = parse_jsonl_entry(entry)
    assert result.content_type == ContentType.TOOL_USE
    assert result.tool_name == "Bash"
