# tests/unit/services/test_response_mode.py
"""Tests for ResponseModeService."""

import pytest


def test_thread_info_response_mode_default():
    """ThreadInfo has response_mode field with default 'all'."""
    from codogram.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="test")
    assert thread.response_mode == "all"


def test_project_state_response_mode_default():
    """ProjectState has response_mode field with default 'all'."""
    from codogram.session_manager import ProjectState

    project = ProjectState(project_name="test")
    assert project.response_mode == "all"
