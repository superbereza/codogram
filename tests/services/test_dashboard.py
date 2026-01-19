"""Tests for dashboard service."""
import pytest
from unittest.mock import patch, MagicMock


def test_format_dashboard_empty():
    """Should return empty state message when no projects."""
    from codogram.services.dashboard import format_dashboard

    result = format_dashboard([])

    assert "Пока нет подключённых проектов" in result


def test_format_dashboard_with_projects():
    """Should format projects list."""
    from codogram.services.dashboard import format_dashboard, ProjectInfo

    projects = [
        ProjectInfo(
            chat_name="codogram",
            directory="/home/user/dev/codogram",
            creator="superbereza",
            members=3,
            active_sessions=2,
        ),
    ]

    result = format_dashboard(projects)

    assert "codogram" in result
    assert "/home/user/dev/codogram" in result
    assert "superbereza" in result
    assert "3 участник" in result
    assert "2 сессий" in result


def test_count_active_sessions():
    """Should count total active sessions."""
    from codogram.services.dashboard import count_active_sessions, ProjectInfo

    projects = [
        ProjectInfo("a", "/a", "u", 1, 2),
        ProjectInfo("b", "/b", "u", 1, 3),
    ]

    assert count_active_sessions(projects) == 5
