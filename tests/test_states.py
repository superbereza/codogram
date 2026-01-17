"""Tests for FSM states."""
from codogram.domain.states import StartFlow, RestartFlow, ResetFlow


class TestRestartFlow:
    """Tests for RestartFlow FSM."""

    def test_has_awaiting_confirm(self):
        """RestartFlow.awaiting_confirm exists."""
        assert hasattr(RestartFlow, "awaiting_confirm")


class TestResetFlow:
    """Tests for ResetFlow FSM."""

    def test_has_awaiting_confirm(self):
        """ResetFlow.awaiting_confirm exists."""
        assert hasattr(ResetFlow, "awaiting_confirm")

    def test_has_awaiting_dir_choice(self):
        """ResetFlow.awaiting_dir_choice exists."""
        assert hasattr(ResetFlow, "awaiting_dir_choice")
