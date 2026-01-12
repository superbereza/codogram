"""Tests for create flow service."""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import MagicMock, patch

from codogram.services.create_flow import create_flow_service


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.project_name = "testproject"
    project.cwd = "/tmp/test"
    project.threads = {}
    return project


def test_should_show_prompt_no_name():
    assert create_flow_service.should_show_prompt(None) is True


def test_should_show_prompt_with_name():
    assert create_flow_service.should_show_prompt("mystic") is False


def test_should_show_prompt_empty_string():
    assert create_flow_service.should_show_prompt("") is True


def test_should_show_prompt_whitespace():
    assert create_flow_service.should_show_prompt("   ") is True


def test_get_magic_name(mock_project):
    name = create_flow_service.get_magic_name(mock_project)
    assert name is not None
    assert len(name) > 0


def test_get_magic_name_excludes_existing(mock_project):
    existing_thread = MagicMock()
    existing_thread.name = "arcane"
    mock_project.threads = {1: existing_thread}

    names = [create_flow_service.get_magic_name(mock_project) for _ in range(10)]
    assert "arcane" not in names


def test_validate_name_success(mock_project):
    name, error = create_flow_service.validate_name("my-feature", mock_project)
    assert error is None
    assert name == "my-feature"


def test_validate_name_sanitizes(mock_project):
    name, error = create_flow_service.validate_name("My Feature", mock_project)
    assert error is None
    assert name == "my-feature"


def test_validate_name_empty_after_sanitize(mock_project):
    name, error = create_flow_service.validate_name("!!!", mock_project)
    assert name is None
    assert "Invalid" in error


def test_validate_name_too_long(mock_project):
    long_name = "a" * 100
    name, error = create_flow_service.validate_name(long_name, mock_project)
    assert name is None
    assert "too long" in error


def test_validate_name_already_exists(mock_project):
    existing = MagicMock()
    existing.name = "mystic"
    mock_project.threads = {1: existing}

    name, error = create_flow_service.validate_name("mystic", mock_project)
    assert name is None
    assert "already used" in error


def test_check_branch_preconditions_no_git(mock_project):
    with patch("codogram.services.create_flow.is_git_repo", return_value=False):
        can, error, warning = create_flow_service.check_branch_preconditions(mock_project, "test")
        assert can is False
        assert "Git" in error


def test_check_branch_preconditions_uncommitted(mock_project):
    with patch("codogram.services.create_flow.is_git_repo", return_value=True), \
         patch("codogram.services.create_flow.has_uncommitted_changes", return_value=True):
        can, error, warning = create_flow_service.check_branch_preconditions(mock_project, "test")
        assert can is False
        assert error is None
        assert "Uncommitted" in warning


def test_check_branch_preconditions_success(mock_project):
    with patch("codogram.services.create_flow.is_git_repo", return_value=True), \
         patch("codogram.services.create_flow.has_uncommitted_changes", return_value=False):
        can, error, warning = create_flow_service.check_branch_preconditions(mock_project, "test")
        assert can is True
        assert error is None
        assert warning is None
