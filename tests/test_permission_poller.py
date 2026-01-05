# tests/test_permission_poller.py
import inspect
from codogram.permission_poller import (
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
