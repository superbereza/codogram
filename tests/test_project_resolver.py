import pytest
from pathlib import Path
from telegram_bridge.project_resolver import get_project_name

def test_simple_directory():
    """Directory without git returns its name."""
    result = get_project_name(Path("/dev/personal-agent"))
    assert result == "personal-agent"

def test_git_repo(tmp_path):
    """Git repo returns directory name."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    result = get_project_name(tmp_path)
    assert result == tmp_path.name

def test_worktree(tmp_path):
    """Worktree returns main repo name."""
    git_file = tmp_path / ".git"
    main_repo = Path("/dev/personal-agent")
    git_file.write_text(f"gitdir: {main_repo}/.git/worktrees/feature-x")
    result = get_project_name(tmp_path)
    assert result == "personal-agent"
