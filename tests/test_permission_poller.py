# tests/test_permission_poller.py
import inspect
from codogram.claude.poller import (
    PollerState,
    permission_poller,
    create_poller_task,
    create_poller_task_for_thread,
)


def test_poller_state_enum():
    assert PollerState.IDLE.value == "idle"
    assert PollerState.DEBOUNCING.value == "debouncing"
    assert PollerState.SHOWING.value == "showing"


def test_permission_poller_signature():
    """Unified permission_poller accepts optional thread parameter."""
    sig = inspect.signature(permission_poller)
    params = list(sig.parameters.keys())

    assert "bot" in params
    assert "project" in params
    assert "telegram_queue" in params
    assert "thread" in params

    # thread should have default None
    thread_param = sig.parameters["thread"]
    assert thread_param.default is None


def test_create_poller_task_exists():
    """create_poller_task should exist for project-level polling."""
    assert callable(create_poller_task)


def test_create_poller_task_for_thread_exists():
    """create_poller_task_for_thread should exist for thread-level polling."""
    assert callable(create_poller_task_for_thread)


def test_permission_poller_no_cached_chat_id():
    """permission_poller should not cache chat_id at function start.

    This test uses AST parsing to verify chat_id is not cached,
    allowing it to run without importing the module (avoids config validation).
    """
    import ast
    import os
    from pathlib import Path

    # Determine the source file path relative to this test file
    test_dir = Path(__file__).parent
    source_file = test_dir.parent / "src" / "codogram" / "permission_poller.py"

    # Read source file
    source = source_file.read_text()
    tree = ast.parse(source)

    # Find permission_poller function
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "permission_poller":
            # Get first 50 lines of function body (initialization section)
            func_source = ast.get_source_segment(source, node)
            first_lines = "\n".join(func_source.split("\n")[:50])

            # Should NOT have "chat_id = project.chat_id" as standalone assignment
            assert "chat_id = project.chat_id" not in first_lines, \
                "chat_id should not be cached at function start"
            break


def test_permission_poller_uses_truncate_body():
    """permission_poller.py should import and use truncate_body for verbose setting."""
    import ast
    from pathlib import Path

    # Read source file
    test_dir = Path(__file__).parent
    source_file = test_dir.parent / "src" / "codogram" / "permission_poller.py"
    source = source_file.read_text()

    # Check import exists
    assert "from .utils.truncate import truncate_body" in source, \
        "permission_poller should import truncate_body"

    # Check truncate_body is called
    assert "truncate_body(" in source, \
        "permission_poller should call truncate_body"

    # Check verbose setting is read
    assert "verbose" in source, \
        "permission_poller should use verbose setting"
