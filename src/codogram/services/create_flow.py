"""CreateFlowService - business logic for branch/thread creation."""
from pathlib import Path

from .. import strings
from ..magic_names import get_random_magic_name
from ..git_utils import sanitize_branch_name, max_branch_name_length, is_git_repo, has_uncommitted_changes


class CreateFlowService:
    """Business logic for branch/thread name selection flow."""

    def should_show_prompt(self, name_arg: str | None) -> bool:
        """Check if name prompt should be shown."""
        if name_arg is None:
            return True
        return not name_arg.strip()

    def get_magic_name(self, project) -> str:
        """Generate random magic name not used by project."""
        existing = {t.name for t in project.threads.values()}
        return get_random_magic_name(existing)

    def validate_name(self, name: str, project) -> tuple[str | None, str | None]:
        """Validate and sanitize name.

        Returns:
            (sanitized_name, None) on success
            (None, error_message) on failure
        """
        sanitized = sanitize_branch_name(name)
        if not sanitized:
            return None, strings.VALIDATE_INVALID_NAME

        max_len = max_branch_name_length(project.project_name)
        if len(sanitized) > max_len:
            return None, strings.VALIDATE_NAME_TOO_LONG.format(max_len=max_len)

        existing = {t.name for t in project.threads.values()}
        if sanitized in existing:
            return None, strings.VALIDATE_NAME_EXISTS.format(name=sanitized)

        return sanitized, None

    def check_branch_preconditions(
        self, project, name: str
    ) -> tuple[bool, str | None, str | None]:
        """Check if branch can be created.

        Returns:
            (can_create, error, warning)
            - error: fatal, cannot proceed
            - warning: can proceed with user confirmation (e.g. uncommitted changes)
        """
        if not is_git_repo(Path(project.cwd)):
            return False, strings.VALIDATE_GIT_REQUIRED, None

        if has_uncommitted_changes(Path(project.cwd)):
            return False, None, strings.VALIDATE_UNCOMMITTED

        return True, None, None


# Module-level singleton
create_flow_service = CreateFlowService()
