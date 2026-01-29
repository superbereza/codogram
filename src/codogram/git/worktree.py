"""Git worktree operations."""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .utils import branch_exists


@dataclass
class WorktreeResult:
    success: bool
    error: str | None = None


def create_worktree(
    main_repo: Path,
    worktree_path: Path,
    branch_name: str,
    base_branch: str
) -> WorktreeResult:
    """Create a new worktree with a new branch."""
    if worktree_path.exists():
        return WorktreeResult(False, f"Directory {worktree_path} already exists")

    if branch_exists(main_repo, branch_name):
        return WorktreeResult(False, f"Branch '{branch_name}' already exists")

    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_path), base_branch],
        cwd=main_repo,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return WorktreeResult(False, result.stderr.strip())

    return WorktreeResult(True)


def remove_worktree(
    main_repo: Path,
    worktree_path: Path,
    branch_name: str,
    delete_branch: bool = True,
    force: bool = False
) -> WorktreeResult:
    """Remove worktree and optionally delete branch."""

    # Remove worktree
    if worktree_path.exists():
        cmd = ["git", "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))

        result = subprocess.run(cmd, cwd=main_repo, capture_output=True, text=True)
        if result.returncode != 0:
            return WorktreeResult(False, result.stderr.strip())

    # Delete branch
    if delete_branch and branch_name and branch_exists(main_repo, branch_name):
        flag = "-D" if force else "-d"
        result = subprocess.run(
            ["git", "branch", flag, branch_name],
            cwd=main_repo,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return WorktreeResult(False, result.stderr.strip())

    return WorktreeResult(True)


def merge_branch(
    main_repo: Path,
    source_branch: str,
    target_branch: str
) -> WorktreeResult:
    """Merge source branch into target branch."""
    # Checkout target
    result = subprocess.run(
        ["git", "checkout", target_branch],
        cwd=main_repo,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return WorktreeResult(False, f"Failed to checkout {target_branch}: {result.stderr}")

    # Merge
    result = subprocess.run(
        ["git", "merge", source_branch],
        cwd=main_repo,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
            return WorktreeResult(False, "Merge conflicts detected")
        return WorktreeResult(False, result.stderr.strip())

    return WorktreeResult(True)


def push_branch(main_repo: Path, branch_name: str) -> WorktreeResult:
    """Push branch to origin."""
    # Check if remote exists
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=main_repo,
        capture_output=True
    )
    if result.returncode != 0:
        return WorktreeResult(True)  # No remote, skip silently

    result = subprocess.run(
        ["git", "push", "origin", branch_name],
        cwd=main_repo,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return WorktreeResult(False, result.stderr.strip())

    return WorktreeResult(True)
