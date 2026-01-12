"""Tests for /branch command prompt behavior."""
import os
# Set env vars BEFORE importing codogram modules
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from aiogram.types import Message, Chat

from codogram.handlers.common import get_flow_state, clear_flow_state


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = -100123
    msg.chat.type = "supergroup"
    msg.chat.is_forum = True
    msg.message_thread_id = 456
    msg.bot = MagicMock()
    return msg


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.cwd = "/tmp/test-project"
    project.project_name = "test-project"
    project.threads = {}
    return project


@pytest.fixture
def mock_queue():
    queue = AsyncMock()
    return queue


@pytest.mark.asyncio
async def test_branch_without_arg_shows_prompt(mock_message, mock_project, mock_queue):
    """/branch without argument shows name prompt with buttons."""
    from codogram.handlers.branches import cmd_branch_create

    mock_message.text = "/branch"

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        # Should set awaiting state
        state = get_flow_state(-100123, 456)
        assert state is not None
        assert state["type"] == "awaiting_create_name"
        assert state["create_type"] == "branch"

        # Should reply with prompt and keyboard
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "Branch name?" in call_args[0][1]
        assert call_args[1]["reply_markup"] is not None

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_branch_with_name_validates_and_creates(mock_message, mock_project, mock_queue):
    """/branch mystic validates and creates branch directly."""
    from codogram.handlers.branches import cmd_branch_create

    mock_message.text = "/branch mystic"

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True), \
         patch("codogram.handlers.branches.branch_exists", return_value=False), \
         patch("codogram.handlers.branches.has_uncommitted_changes", return_value=False), \
         patch("codogram.handlers.branches.get_default_branch", return_value="main"), \
         patch("codogram.handlers.branches.do_branch_create") as mock_create:
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        # Should NOT set awaiting state
        state = get_flow_state(-100123, 456)
        assert state is None

        # Should create branch directly
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][3] == "mystic"  # branch_name

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_branch_with_invalid_name_shows_error(mock_message, mock_project, mock_queue):
    """/branch with invalid name shows validation error."""
    from codogram.handlers.branches import cmd_branch_create

    # Use a very long name that exceeds max length
    mock_message.text = "/branch " + "a" * 100

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        # Should reply with error
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "too long" in call_args[0][1]

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_branch_create_also_shows_prompt(mock_message, mock_project, mock_queue):
    """/branch_create without argument shows name prompt."""
    from codogram.handlers.branches import cmd_branch_create

    mock_message.text = "/branch_create"

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        state = get_flow_state(-100123, 456)
        assert state is not None
        assert state["type"] == "awaiting_create_name"

    clear_flow_state(-100123, 456)


@pytest.mark.asyncio
async def test_branch_with_duplicate_name_shows_error(mock_message, mock_project, mock_queue):
    """/branch with existing branch name shows error."""
    from codogram.handlers.branches import cmd_branch_create

    mock_message.text = "/branch existing"

    with patch("codogram.handlers.branches.project_manager") as mock_pm, \
         patch("codogram.handlers.branches.is_git_repo", return_value=True), \
         patch("codogram.handlers.branches.branch_exists", return_value=True):
        mock_pm.get_by_chat.return_value = mock_project

        await cmd_branch_create(mock_message, mock_queue)

        # Should reply with error about existing branch
        mock_queue.reply.assert_called_once()
        call_args = mock_queue.reply.call_args
        assert "already exists" in call_args[0][1]

    clear_flow_state(-100123, 456)
