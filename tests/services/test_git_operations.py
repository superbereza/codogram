# tests/services/test_git_operations.py
import pytest
from unittest.mock import patch, AsyncMock

from codogram.services.setup.git_operations import (
    git_init,
    check_gh_cli,
    extract_project_name_from_url,
)


def test_extract_project_name_https():
    """Extract name from HTTPS URL."""
    url = "https://github.com/user/awesome-project.git"
    assert extract_project_name_from_url(url) == "awesome-project"


def test_extract_project_name_ssh():
    """Extract name from SSH URL."""
    url = "git@github.com:user/awesome-project.git"
    assert extract_project_name_from_url(url) == "awesome-project"


def test_extract_project_name_no_git_suffix():
    """Extract name without .git suffix."""
    url = "https://github.com/user/awesome-project"
    assert extract_project_name_from_url(url) == "awesome-project"


@pytest.mark.asyncio
async def test_git_init_creates_repo(tmp_path):
    """git_init creates .git directory."""
    result = await git_init(tmp_path)
    assert result.success
    assert (tmp_path / ".git").exists()


@pytest.mark.asyncio
async def test_check_gh_cli_not_installed():
    """check_gh_cli returns error when gh not found."""
    with patch("shutil.which", return_value=None):
        result = await check_gh_cli()
        assert not result.success
        assert "not installed" in result.error.lower()
