# tests/test_history_reader.py
import json
import tempfile
from pathlib import Path
from codogram.claude.session_finder import find_session_for_project, reset_history_cache, compute_jsonl_path, get_session_creation_time

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

def test_compute_jsonl_path():
    result = compute_jsonl_path("/home/user/dev/my-project", "abc-123-def")
    expected = Path.home() / ".claude" / "projects" / "-home-user-dev-my-project" / "abc-123-def.jsonl"
    assert result == expected

def test_compute_jsonl_path_root():
    result = compute_jsonl_path("/", "test-session")
    expected = Path.home() / ".claude" / "projects" / "-" / "test-session.jsonl"
    assert result == expected

def test_compute_jsonl_path_trailing_slash():
    """Trailing slash should be normalized."""
    result1 = compute_jsonl_path("/home/user/project", "abc")
    result2 = compute_jsonl_path("/home/user/project/", "abc")
    assert result1 == result2

def test_compute_jsonl_path_double_slash():
    """Double slashes should be normalized."""
    result1 = compute_jsonl_path("/home/user/project", "abc")
    result2 = compute_jsonl_path("/home//user//project", "abc")
    assert result1 == result2

def test_compute_jsonl_path_symlink_not_resolved():
    """Symlinks should NOT be resolved (match Claude behavior)."""
    # Claude uses raw cwd, not resolved path
    result = compute_jsonl_path("/home/user/link-to-project", "abc")
    assert "-home-user-link-to-project" in str(result)


def test_get_session_creation_time():
    """Test reading session creation time from first entry timestamp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "test-session.jsonl"
        timestamp = 1703847600.123  # Fixed timestamp for test

        with open(jsonl_path, 'w') as f:
            f.write(json.dumps({"type": "system", "timestamp": timestamp}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": timestamp + 1}) + "\n")

        result = get_session_creation_time(jsonl_path)
        assert result == timestamp


def test_get_session_creation_time_missing_file():
    """Return 0 for missing file."""
    result = get_session_creation_time(Path("/nonexistent/path.jsonl"))
    assert result == 0


def test_get_session_creation_time_empty_file():
    """Return 0 for empty file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "empty.jsonl"
        jsonl_path.touch()

        result = get_session_creation_time(jsonl_path)
        assert result == 0


def test_get_session_creation_time_no_timestamp():
    """Return 0 if first entry has no timestamp field."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "no-ts.jsonl"
        with open(jsonl_path, 'w') as f:
            f.write(json.dumps({"type": "system"}) + "\n")

        result = get_session_creation_time(jsonl_path)
        assert result == 0


def test_get_session_creation_time_malformed_json():
    """Return 0 for malformed JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "bad.jsonl"
        with open(jsonl_path, 'w') as f:
            f.write("not valid json\n")

        result = get_session_creation_time(jsonl_path)
        assert result == 0


def test_find_session_by_user_message_filters_by_created_after(tmp_path, monkeypatch):
    """Test that created_after filters out old sessions."""
    import os
    from codogram.claude.session_finder import find_session_by_user_message

    # Create project directory structure
    project_dir = tmp_path / ".claude" / "projects" / "-test-cwd"
    project_dir.mkdir(parents=True)

    # Old session (created at t=100)
    old_session = project_dir / "old-session.jsonl"
    with open(old_session, 'w') as f:
        f.write(json.dumps({"type": "system", "timestamp": 100}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n")
    # Set mtime to old time (ensure it's sorted as "older")
    os.utime(old_session, (100, 100))

    # New session (created at t=200)
    new_session = project_dir / "new-session.jsonl"
    with open(new_session, 'w') as f:
        f.write(json.dumps({"type": "system", "timestamp": 200}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n")
    # Set mtime to newer time (ensure it's sorted as "newer")
    os.utime(new_session, (200, 200))

    # Patch Path.home using monkeypatch (proper pytest way)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)

    # Without filter: should find new-session (newest by mtime)
    result = find_session_by_user_message("/test/cwd", "Hello")
    assert result is not None
    session_id, _ = result
    assert session_id == "new-session"

    # With created_after=150: should find new-session (created at 200 > 150)
    result = find_session_by_user_message("/test/cwd", "Hello", created_after=150)
    assert result is not None
    session_id, _ = result
    assert session_id == "new-session"

    # With created_after=250: should find nothing (both too old)
    result = find_session_by_user_message("/test/cwd", "Hello", created_after=250)
    assert result is None
