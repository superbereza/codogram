# tests/test_git_utils.py
import subprocess
from pathlib import Path


def test_sanitize_branch_name():
    from codogram.git_utils import sanitize_branch_name

    assert sanitize_branch_name("feature/auth") == "feature-auth"
    assert sanitize_branch_name("fix login bug") == "fix-login-bug"
    assert sanitize_branch_name("feature@#$auth") == "featureauth"
    assert sanitize_branch_name("UPPER-case") == "upper-case"


def test_get_default_branch(tmp_path, monkeypatch):
    from codogram.git_utils import get_default_branch

    # Create a git repo with main branch
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
    (tmp_path / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    assert get_default_branch(tmp_path) == "main"


def test_branch_exists(tmp_path):
    from codogram.git_utils import branch_exists

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
    (tmp_path / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    assert branch_exists(tmp_path, "main") is True
    assert branch_exists(tmp_path, "nonexistent") is False


def test_has_uncommitted_changes(tmp_path):
    from codogram.git_utils import has_uncommitted_changes

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
    (tmp_path / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    assert has_uncommitted_changes(tmp_path) is False

    (tmp_path / "file.txt").write_text("modified")
    assert has_uncommitted_changes(tmp_path) is True


def test_is_git_repo(tmp_path):
    from codogram.git_utils import is_git_repo

    assert is_git_repo(tmp_path) is False

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    assert is_git_repo(tmp_path) is True


def test_max_branch_name_length():
    from codogram.git_utils import max_branch_name_length

    assert max_branch_name_length("codogram") == 37  # 45 - 8
    assert max_branch_name_length("my-long-project") == 30  # 45 - 15
