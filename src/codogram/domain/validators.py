"""Domain validators for project names and other inputs."""
import re


def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid.

    Valid names contain only: letters, digits, dash, underscore.
    """
    if not name:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))
