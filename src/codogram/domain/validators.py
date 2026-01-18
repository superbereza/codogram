"""Domain validators for project names and other inputs."""
import re

from unidecode import unidecode

from .. import strings

MAX_PROJECT_NAME_LENGTH = 50


def validate_git_url(url: str) -> tuple[bool, str | None]:
    """Validate git clone URL.

    Returns (is_valid, error_string). Uses precise GitHub patterns
    to avoid false positives on repos with names like 'wiki-parser'.
    """
    # GitHub-specific patterns (match only actual file/tree URLs)
    github_blob = re.compile(r'github\.com/[^/]+/[^/]+/blob/')
    github_tree = re.compile(r'github\.com/[^/]+/[^/]+/tree/')

    if "/wiki/" in url and "github.com" in url:
        return False, strings.GIT_URL_INVALID_WIKI
    if github_blob.search(url) or github_tree.search(url):
        return False, strings.GIT_URL_INVALID_BLOB
    if "gist.github.com" in url:
        return False, strings.GIT_URL_INVALID_GIST
    if not url.startswith(("https://", "git@", "ssh://")):
        return False, strings.GIT_URL_INVALID_FORMAT
    return True, None


def extract_project_name_from_url(url: str) -> str | None:
    """Extract project name from git URL.

    Examples:
        https://github.com/user/awesome-project.git -> awesome-project
        git@github.com:user/awesome-project.git -> awesome-project
        ssh://git@github.com/user/project -> project
    """
    # HTTPS format: https://github.com/user/repo.git
    https_match = re.search(r'/([^/]+?)(?:\.git)?$', url)
    if https_match:
        name = https_match.group(1)
        if name.endswith(".git"):
            name = name[:-4]
        return name

    # SSH format: git@github.com:user/repo.git
    ssh_match = re.search(r':(?:[^/]+/)?([^/]+?)(?:\.git)?$', url)
    if ssh_match:
        name = ssh_match.group(1)
        if name.endswith(".git"):
            name = name[:-4]
        return name

    return None


def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid.

    Valid names:
    - Only letters, digits, dash, underscore
    - Max 50 characters
    - Not empty
    """
    if not name:
        return False
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))


def sanitize_project_name(title: str) -> str | None:
    """Sanitize chat title to valid project name.

    Uses unidecode to transliterate non-ASCII characters.
    Returns None if result is empty or too long.
    """
    if not title:
        return None

    # Transliterate to ASCII
    sanitized = unidecode(title)
    sanitized = sanitized.lower()
    # Replace non-alphanumeric with dashes
    sanitized = re.sub(r'[^a-z0-9_-]', '-', sanitized)
    # Collapse multiple dashes
    sanitized = re.sub(r'-+', '-', sanitized)
    # Strip leading/trailing dashes
    sanitized = sanitized.strip('-')

    if not sanitized or len(sanitized) > MAX_PROJECT_NAME_LENGTH:
        return None

    return sanitized
