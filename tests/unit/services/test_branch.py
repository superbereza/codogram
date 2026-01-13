"""Tests for branch/worktree helper functions."""
import subprocess
from pathlib import Path


class TestWorktreeHelpers:
    def test_create_worktree_from_existing_branch(self, tmp_path):
        """Create worktree when branch already exists."""
        from codogram.services.branch import create_worktree

        # Setup git repo with branch
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "branch", "my-feature"], cwd=tmp_path, check=True)

        success, path = create_worktree(tmp_path, "my-feature")

        assert success
        assert Path(path).exists()
        assert "my-feature" in path

    def test_create_branch_with_worktree(self, tmp_path):
        """Create new branch and worktree from scratch."""
        from codogram.services.branch import create_branch_with_worktree

        # Setup git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)

        success, path = create_branch_with_worktree(tmp_path, "new-feature")

        assert success
        assert Path(path).exists()
        assert "new-feature" in path
