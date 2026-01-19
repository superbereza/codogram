"""FSM states for conversation flows."""
from aiogram.fsm.state import State, StatesGroup


class StartFlow(StatesGroup):
    """States for /start command flow.

    Additional states will be added in Phase 7 when FSM migration happens.
    """

    awaiting_project_name = State()
    awaiting_dir_choice = State()
    awaiting_git_choice = State()
    awaiting_gh_visibility = State()
    awaiting_clone_url = State()
    awaiting_custom_path = State()
    awaiting_launch_confirm = State()


class RestartFlow(StatesGroup):
    """States for /restart confirmation flow."""

    awaiting_confirm = State()


class ResetFlow(StatesGroup):
    """FSM states for /reset_all flow."""

    awaiting_confirm = State()
    awaiting_dir_choice = State()


class SetupFlow(StatesGroup):
    """States for new onboarding flow (v2).

    See docs/designs/2026-01-18-start-flow-v2.md for flow diagrams.
    """

    awaiting_admin_rights = State()
    awaiting_setup_type = State()        # Clone/Connect/New
    awaiting_clone_url = State()
    awaiting_folder_select = State()     # pagination in callback_data
    viewing_connected_projects = State()
    awaiting_project_name = State()
    awaiting_git_choice = State()
    awaiting_rename_confirm = State()    # Offer to rename chat
    launching = State()                   # Blocking state during launch
