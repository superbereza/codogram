# tests/services/test_folder_list.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from codogram.services.setup.folder_list import (
    list_available_folders,
    get_connected_folders,
    get_chat_link,
)


def test_list_available_folders_excludes_hidden(tmp_path):
    """Hidden folders are excluded."""
    (tmp_path / "visible").mkdir()
    (tmp_path / ".hidden").mkdir()

    folders = list_available_folders(tmp_path, connected=set())
    assert "visible" in folders
    assert ".hidden" not in folders


def test_list_available_folders_excludes_connected(tmp_path):
    """Already connected folders are excluded."""
    (tmp_path / "project1").mkdir()
    (tmp_path / "project2").mkdir()

    folders = list_available_folders(tmp_path, connected={"project1"})
    assert "project1" not in folders
    assert "project2" in folders


def test_list_available_folders_excludes_symlinks(tmp_path):
    """Symlinks are excluded."""
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")

    folders = list_available_folders(tmp_path, connected=set())
    assert "real" in folders
    assert "link" not in folders


def test_list_available_folders_sorted(tmp_path):
    """Folders are sorted alphabetically."""
    (tmp_path / "zebra").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()

    folders = list_available_folders(tmp_path, connected=set())
    assert folders == ["alpha", "beta", "zebra"]


def test_get_chat_link_supergroup():
    """Supergroup chat_id converts to t.me/c link."""
    link = get_chat_link(-1001234567890, "supergroup")
    assert link == "https://t.me/c/1234567890"


def test_get_chat_link_regular_group_returns_none():
    """Regular groups don't have stable links."""
    link = get_chat_link(-123456789, "group")
    assert link is None
