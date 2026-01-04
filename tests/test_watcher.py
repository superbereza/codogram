# tests/test_watcher.py
import pytest
import json
import tempfile
from pathlib import Path

from codogram.watcher import parse_jsonl_entry, ContentType

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

def test_parse_jsonl_entry_handles_string_in_content():
    """content может содержать строки, не только dict."""
    entry = {
        "type": "user",
        "message": {
            "content": ["string item", {"type": "tool_result", "content": "result"}]
        }
    }
    result = parse_jsonl_entry(entry)
    assert result is not None
    assert result.content_type == ContentType.TOOL_RESULT

def test_parse_jsonl_entry_handles_string_in_assistant_content():
    entry = {
        "type": "assistant",
        "message": {
            "content": ["string item", {"type": "text", "text": "hello"}]
        }
    }
    result = parse_jsonl_entry(entry)
    assert result is not None
    assert result.content_type == ContentType.TEXT
