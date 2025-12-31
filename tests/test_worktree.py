# tests/test_worktree.py
import subprocess
from pathlib import Path


def test_create_worktree(tmp_path):
    from codogram.worktree import create_worktree

    # Setup main repo
    main_repo = tmp_path / "project"
    main_repo.mkdir()
    subprocess.run(["git", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=main_repo, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, capture_output=True)

    worktree_path = tmp_path / "project-feature"

    result = create_worktree(
        main_repo=main_repo,
        worktree_path=worktree_path,
        branch_name="feature",
        base_branch="main"
    )

    assert result.success is True
    assert worktree_path.exists()
    assert (worktree_path / "file.txt").exists()


def test_create_worktree_branch_exists(tmp_path):
    from codogram.worktree import create_worktree

    main_repo = tmp_path / "project"
    main_repo.mkdir()
    subprocess.run(["git", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=main_repo, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=main_repo, capture_output=True)

    worktree_path = tmp_path / "project-feature"

    result = create_worktree(
        main_repo=main_repo,
        worktree_path=worktree_path,
        branch_name="feature",
        base_branch="main"
    )

    assert result.success is False
    assert "already exists" in result.error


def test_remove_worktree(tmp_path):
    from codogram.worktree import create_worktree, remove_worktree

    main_repo = tmp_path / "project"
    main_repo.mkdir()
    subprocess.run(["git", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=main_repo, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, capture_output=True)

    worktree_path = tmp_path / "project-feature"
    create_worktree(main_repo, worktree_path, "feature", "main")

    result = remove_worktree(main_repo, worktree_path, "feature", delete_branch=True)

    assert result.success is True
    assert not worktree_path.exists()


def test_merge_branch(tmp_path):
    from codogram.worktree import create_worktree, merge_branch

    main_repo = tmp_path / "project"
    main_repo.mkdir()
    subprocess.run(["git", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=main_repo, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, capture_output=True)

    worktree_path = tmp_path / "project-feature"
    create_worktree(main_repo, worktree_path, "feature", "main")

    # Make changes in worktree
    (worktree_path / "new_file.txt").write_text("new")
    subprocess.run(["git", "add", "."], cwd=worktree_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add new file"], cwd=worktree_path, capture_output=True)

    result = merge_branch(main_repo, "feature", "main")

    assert result.success is True
    assert (main_repo / "new_file.txt").exists()
