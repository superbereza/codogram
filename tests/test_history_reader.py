# tests/test_history_reader.py
import json
import tempfile
from pathlib import Path
from telegram_bridge.history_reader import find_session_for_project, reset_history_cache

def test_find_session_for_project():
    reset_history_cache()  # Clean state

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({"project": "/home/user/project-a", "sessionId": "aaa-111"}) + "\n")
        f.write(json.dumps({"project": "/home/user/project-b", "sessionId": "bbb-222"}) + "\n")
        f.write(json.dumps({"project": "/home/user/project-a", "sessionId": "aaa-333"}) + "\n")
        history_path = Path(f.name)

    try:
        # Should return last session for project-a
        result = find_session_for_project("/home/user/project-a", history_path)
        assert result == "aaa-333"

        # Should return session for project-b
        result = find_session_for_project("/home/user/project-b", history_path)
        assert result == "bbb-222"

        # Should return None for unknown project
        result = find_session_for_project("/home/user/unknown", history_path)
        assert result is None
    finally:
        history_path.unlink()

def test_find_session_empty_file():
    reset_history_cache()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)

    try:
        result = find_session_for_project("/any/path", history_path)
        assert result is None
    finally:
        history_path.unlink()

def test_incremental_reading():
    """Test that incremental reading works correctly."""
    reset_history_cache()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)
        f.write(json.dumps({"project": "/test", "sessionId": "first"}) + "\n")
        f.flush()

        try:
            # First read
            result = find_session_for_project("/test", history_path)
            assert result == "first"

            # Append new entry
            f.write(json.dumps({"project": "/test", "sessionId": "second"}) + "\n")
            f.flush()

            # Should pick up new entry
            result = find_session_for_project("/test", history_path)
            assert result == "second"
        finally:
            history_path.unlink()

def test_truncated_file_detection():
    """Test that file truncation is detected and cache is reset."""
    reset_history_cache()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)
        # Write initial data
        f.write(json.dumps({"project": "/test", "sessionId": "first"}) + "\n")
        f.write(json.dumps({"project": "/test", "sessionId": "second"}) + "\n")
        f.flush()

        try:
            # First read
            result = find_session_for_project("/test", history_path)
            assert result == "second"

            # Simulate truncation - rewrite file with less data
            f.close()
            with open(history_path, 'w') as f2:
                f2.write(json.dumps({"project": "/test", "sessionId": "third"}) + "\n")

            # Should detect truncation and re-read from start
            result = find_session_for_project("/test", history_path)
            assert result == "third"
        finally:
            history_path.unlink()

def test_malformed_json_handling():
    """Test that malformed JSON lines are skipped."""
    reset_history_cache()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        history_path = Path(f.name)
        f.write(json.dumps({"project": "/test", "sessionId": "first"}) + "\n")
        f.write("not valid json\n")
        f.write(json.dumps({"project": "/test", "sessionId": "second"}) + "\n")
        f.flush()

        try:
            result = find_session_for_project("/test", history_path)
            assert result == "second"
        finally:
            history_path.unlink()
