"""Setup flow keyboards."""
from .setup_type import admin_check_keyboard, setup_type_keyboard
from .common import go_back_keyboard, clone_error_keyboard, folder_exists_keyboard
from .folder_select import folder_select_keyboard, connected_projects_keyboard, FOLDERS_PER_PAGE
from .git_choice import git_choice_keyboard, visibility_keyboard
from .confirm import rename_confirm_keyboard

__all__ = [
    "setup_type_keyboard",
    "admin_check_keyboard",
    "go_back_keyboard",
    "clone_error_keyboard",
    "folder_exists_keyboard",
    "folder_select_keyboard",
    "connected_projects_keyboard",
    "FOLDERS_PER_PAGE",
    "git_choice_keyboard",
    "visibility_keyboard",
    "rename_confirm_keyboard",
]
