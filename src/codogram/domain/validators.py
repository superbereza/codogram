"""Domain validators for project names and other inputs."""
import re

MAX_PROJECT_NAME_LENGTH = 35


def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid.

    Valid names:
    - Only letters, digits, dash, underscore
    - Max 35 characters
    - Not empty
    """
    if not name:
        return False
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))


def sanitize_project_name(title: str) -> str | None:
    """Convert chat title to valid project name.

    - Replaces invalid chars with dashes
    - Collapses multiple dashes
    - Strips leading/trailing dashes
    - Returns None if result is empty or too long
    """
    if not title:
        return None

    # Replace invalid chars with dash
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', title)
    # Collapse multiple dashes
    sanitized = re.sub(r'-+', '-', sanitized)
    # Strip leading/trailing dashes
    sanitized = sanitized.strip('-')

    if not sanitized:
        return None
    if len(sanitized) > MAX_PROJECT_NAME_LENGTH:
        return None

    return sanitized
