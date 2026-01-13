# src/codogram/domain/worktree_state.py
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codogram.session_manager import ThreadInfo


class WorktreeState(Enum):
    OK = "ok"
    MISSING_WITH_BRANCH = "missing_with_branch"
    MISSING_NO_BRANCH = "missing_no_branch"


def get_worktree_state(thread: ThreadInfo, project_cwd: Path) -> WorktreeState:
    """Check worktree state for a thread."""
    from codogram.git_utils import branch_exists

    if not thread.worktree_path:
        return WorktreeState.OK

    if Path(thread.worktree_path).exists():
        return WorktreeState.OK

    if branch_exists(project_cwd, thread.name):
        return WorktreeState.MISSING_WITH_BRANCH

    return WorktreeState.MISSING_NO_BRANCH
