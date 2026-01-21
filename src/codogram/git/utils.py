"""Git utility functions for worktree support."""
import re
import subprocess
from pathlib import Path

from unidecode import unidecode


def sanitize_branch_name(name: str) -> str:
    """Sanitize branch name: lowercase, transliterate, replace invalid chars."""
    name = unidecode(name)  # transliterate any language to ASCII
    name = name.lower()
    name = re.sub(r'[/\s]+', '-', name)  # slashes and spaces to dashes
    name = re.sub(r'[^a-z0-9_-]', '', name)  # remove invalid chars
    return name


def get_default_branch(repo_path: Path) -> str:
    """Get default branch name (main, master, etc.)."""
    # Try remote HEAD first
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return result.stdout.strip().split('/')[-1]

    # Try local config
    result = subprocess.run(
        ["git", "config", "--get", "init.defaultBranch"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # Check if main exists
    if branch_exists(repo_path, "main"):
        return "main"

    # Check if master exists
    if branch_exists(repo_path, "master"):
        return "master"

    # Fallback to current branch
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    return "main"  # ultimate fallback


def branch_exists(repo_path: Path, branch_name: str) -> bool:
    """Check if branch exists in repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        cwd=repo_path,
        capture_output=True
    )
    return result.returncode == 0


def has_uncommitted_changes(repo_path: Path) -> bool:
    """Check if repo has uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


def is_git_repo(path: Path) -> bool:
    """Check if path is a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=path,
        capture_output=True
    )
    return result.returncode == 0


def has_any_commits(repo_path: Path) -> bool:
    """Check if repo has at least one commit."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True
    )
    return result.returncode == 0


def max_branch_name_length(project_name: str) -> int:
    """Calculate max branch name length for project."""
    return 45 - len(project_name)
