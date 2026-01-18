"""Setup flow services."""
from .admin_rights import check_bot_admin_rights
from .base_dir import check_base_dir
from .folder_list import list_available_folders, get_connected_folders, get_chat_link
from .git_operations import git_init, check_gh_cli, gh_repo_create, extract_project_name_from_url, GitResult
from .chat_rename import rename_chat_safe

__all__ = [
    "check_bot_admin_rights",
    "check_base_dir",
    "list_available_folders",
    "get_connected_folders",
    "get_chat_link",
    "git_init",
    "check_gh_cli",
    "gh_repo_create",
    "extract_project_name_from_url",
    "GitResult",
    "rename_chat_safe",
]
