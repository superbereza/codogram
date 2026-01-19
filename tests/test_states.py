"""Tests for FSM states."""
from codogram.domain.states import StartFlow, RestartFlow, ResetFlow, SetupFlow


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


class TestSetupFlow:
    """Tests for SetupFlow FSM (v2 onboarding)."""

    def test_setup_flow_has_all_states(self):
        """SetupFlow has all required states."""
        assert hasattr(SetupFlow, 'awaiting_admin_rights')
        assert hasattr(SetupFlow, 'awaiting_setup_type')
        assert hasattr(SetupFlow, 'awaiting_clone_url')
        assert hasattr(SetupFlow, 'awaiting_folder_select')
        assert hasattr(SetupFlow, 'viewing_connected_projects')
        assert hasattr(SetupFlow, 'awaiting_project_name')
        assert hasattr(SetupFlow, 'awaiting_git_choice')
        assert hasattr(SetupFlow, 'launching')
