"""Tests for FSM states."""
from codogram.domain.states import StartFlow, RestartFlow


class TestRestartFlow:
    """Tests for RestartFlow FSM."""

    def test_has_awaiting_confirm(self):
        """RestartFlow.awaiting_confirm exists."""
        assert hasattr(RestartFlow, "awaiting_confirm")
