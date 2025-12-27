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


# Tests for find_missed_entries

from codogram.watcher import find_missed_entries, ParsedEntry


def test_find_missed_entries_returns_entries_after_last_user():
    """Should return all assistant entries after last user message."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({"type": "user", "message": {"content": []}}) + '\n')
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}) + '\n')
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}}) + '\n')
        path = Path(f.name)

    entries = find_missed_entries(path)

    assert len(entries) == 2
    assert entries[0].content_type == ContentType.TEXT
    assert entries[1].content_type == ContentType.TOOL_USE

    path.unlink()


def test_find_missed_entries_resets_on_new_user_message():
    """Should only return entries after the LAST user message."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({"type": "user", "message": {"content": []}}) + '\n')
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "First"}]}}) + '\n')
        f.write(json.dumps({"type": "user", "message": {"content": []}}) + '\n')
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Second"}]}}) + '\n')
        path = Path(f.name)

    entries = find_missed_entries(path)

    assert len(entries) == 1
    assert entries[0].text == "Second"

    path.unlink()


def test_find_missed_entries_empty_file():
    """Should return empty list for empty file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        path = Path(f.name)

    entries = find_missed_entries(path)

    assert entries == []

    path.unlink()


def test_find_missed_entries_file_not_exists():
    """Should return empty list if file doesn't exist."""
    path = Path("/nonexistent/file.jsonl")

    entries = find_missed_entries(path)

    assert entries == []
