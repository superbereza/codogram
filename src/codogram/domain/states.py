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
