"""Tests for StartFlowService."""
import pytest

from codogram.services.start_flow import FlowAction, FlowResult


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
