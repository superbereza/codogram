"""Tests for StartFlowService."""
import os
from unittest.mock import Mock, patch

import pytest

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from codogram.services.start_flow import FlowAction, FlowResult, StartFlowService


class TestFlowAction:
    def test_has_ask_project_name(self):
        assert FlowAction.ASK_PROJECT_NAME.value == "ask_project_name"

    def test_has_error(self):
        assert FlowAction.ERROR.value == "error"

    def test_has_launch(self):
        assert FlowAction.LAUNCH.value == "launch"


class TestFlowResult:
    def test_default_values(self):
        result = FlowResult(action=FlowAction.ERROR)
        assert result.action == FlowAction.ERROR
        assert result.project is None
        assert result.path is None
        assert result.error is None

    def test_with_all_fields(self):
        result = FlowResult(
            action=FlowAction.ASK_DIR_CHOICE,
            project="my-project",
            path="/tmp/my-project",
            message="Choose action",
        )
        assert result.project == "my-project"
        assert result.path == "/tmp/my-project"


class TestHandleStartWithProjectName:
    """Tests for handle_start when project name is provided in args."""

    def test_valid_project_name_no_existing_dir(self):
        """Valid project name, directory doesn't exist -> ASK_DIR_CHOICE."""
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/my-project", exists=False)
            result = service.handle_start(chat_id=123, args=["my-project"])

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "my-project"
        assert result.path == "/tmp/my-project"

    def test_invalid_project_name_with_space(self):
        """Project name with space -> ERROR."""
        service = StartFlowService(Mock(), Mock())

        result = service.handle_start(chat_id=123, args=["my project"])

        assert result.action == FlowAction.ERROR
        assert "letters, digits" in result.error.lower() or "only contain" in result.error.lower()

    def test_project_name_too_long(self):
        """Project name > 35 chars -> ERROR."""
        service = StartFlowService(Mock(), Mock())

        result = service.handle_start(chat_id=123, args=["a" * 40])

        assert result.action == FlowAction.ERROR
        assert "too long" in result.error.lower()


class TestHandleStartNoArgs:
    """Tests for handle_start when no args provided."""

    def test_no_project_no_title_asks_name(self):
        """No project, no chat title -> ASK_PROJECT_NAME."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_start(chat_id=123, args=[], chat_title=None)

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_uses_chat_title_if_valid(self):
        """No project, valid chat title -> start flow with sanitized title."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/My-Project", exists=False)
            result = service.handle_start(
                chat_id=123, args=[], chat_title="My Project!"
            )

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "My-Project"

    def test_ignores_invalid_chat_title(self):
        """Chat title that sanitizes to empty -> ASK_PROJECT_NAME."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_start(chat_id=123, args=[], chat_title="!!!")

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_existing_project_not_running(self):
        """Existing project for chat, not running -> start flow."""
        mock_pm = Mock()
        existing = Mock(
            project_name="existing-project",
            cwd=None,
            chat_id=123,
            tmux_session=None,
        )
        mock_pm.get_by_chat.return_value = existing
        mock_pm.get_or_create.return_value = existing

        service = StartFlowService(mock_pm, Mock())

        with patch(
            "codogram.services.start_flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(
                path="/tmp/existing-project", exists=False
            )
            result = service.handle_start(chat_id=123, args=[])

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "existing-project"
