# tests/test_watcher.py
import pytest
import json
import tempfile
from pathlib import Path

from codogram.watcher import parse_jsonl_entry, ContentType
from codogram.strings import SNIP

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


from codogram.watcher import format_tool_use


def test_format_tool_use_bash_truncates_in_short_mode():
    """Bash command should be truncated when verbose=False."""
    long_cmd = "\n".join([f"echo line{i}" for i in range(10)])
    result = format_tool_use("Bash", {"command": long_cmd}, verbose=False)
    # Should truncate the command to 5 lines + SNIP
    assert SNIP in result
    # Original 10 lines should NOT be fully present
    assert "echo line9" not in result


def test_format_tool_use_bash_full_in_verbose_mode():
    """Bash command should be full when verbose=True."""
    long_cmd = "\n".join([f"echo line{i}" for i in range(10)])
    result = format_tool_use("Bash", {"command": long_cmd}, verbose=True)
    # All 10 lines should be present
    assert "echo line9" in result
    assert SNIP not in result
