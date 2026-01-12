"""Tests for flow state management."""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from codogram.handlers.common import (
    get_flow_state,
    set_flow_state,
    clear_flow_state,
    clear_flow_state_by_type,
    has_flow_state,
)


def test_set_and_get_state():
    set_flow_state(-100, 456, {"type": "test", "data": "value"})
    state = get_flow_state(-100, 456)
    assert state is not None
    assert state["type"] == "test"
    clear_flow_state(-100, 456)


def test_get_state_returns_none_when_empty():
    clear_flow_state(-100, 999)
    assert get_flow_state(-100, 999) is None


def test_different_threads_independent():
    """State in different threads should not conflict."""
    set_flow_state(-100, 1, {"type": "a"})
    set_flow_state(-100, 2, {"type": "b"})

    assert get_flow_state(-100, 1)["type"] == "a"
    assert get_flow_state(-100, 2)["type"] == "b"

    clear_flow_state(-100, 1)
    clear_flow_state(-100, 2)


def test_none_thread_id():
    """None thread_id (General topic) works correctly."""
    set_flow_state(-100, None, {"type": "general"})
    assert get_flow_state(-100, None)["type"] == "general"
    clear_flow_state(-100, None)


def test_clear_flow_state_by_type():
    """Clear only states of specific type."""
    set_flow_state(-100, 1, {"type": "awaiting_create_name"})
    set_flow_state(-100, 2, {"type": "other"})

    clear_flow_state_by_type(-100, 1, "awaiting_create_name")

    assert get_flow_state(-100, 1) is None
    assert get_flow_state(-100, 2) is not None

    clear_flow_state(-100, 2)


def test_has_flow_state():
    clear_flow_state(-100, 1)
    assert has_flow_state(-100, 1) is False

    set_flow_state(-100, 1, {"type": "test"})
    assert has_flow_state(-100, 1) is True

    clear_flow_state(-100, 1)
