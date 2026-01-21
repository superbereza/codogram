# tests/test_launch_animation.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from codogram.telegram.launch_animation import FACES, FACE_READY


def test_faces_are_unique():
    """All faces in FACES list are unique."""
    assert len(FACES) == len(set(FACES))


def test_face_ready_not_in_faces():
    """FACE_READY is distinct from animation faces."""
    assert FACE_READY not in FACES


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.cwd = "/home/user/project"
    project.project_name = "test-project"
    return project


@pytest.fixture
def mock_thread():
    thread = MagicMock()
    thread.name = "feature-x"
    thread.worktree_path = "/home/user/project/.worktrees/feature-x"
    thread.session_id = "abc-123-def"
    thread.awaiting_new_session = False
    thread.start_requested_at = None
    thread.launch_task = None
    thread.poller_task = None
    thread.get_tmux_session = MagicMock(return_value="test-project-feature-x")
    return thread


@pytest.mark.asyncio
async def test_launch_with_session_id_uses_resume_flag(mock_project, mock_thread):
    """When session_id provided, should use 'claude --resume {id}'."""
    from codogram.telegram.launch_animation import launch_with_animation

    bot = AsyncMock()
    queue = AsyncMock()
    queue.send = AsyncMock(return_value=[123])

    with patch("codogram.telegram.launch_animation.TmuxSession") as MockTmux, \
         patch("codogram.telegram.launch_animation.project_manager"), \
         patch("codogram.telegram.launch_animation._start_monitoring"):

        mock_tmux = MagicMock()
        mock_tmux.exists.return_value = False
        mock_tmux.is_claude_ready.return_value = True  # Skip wait loop
        MockTmux.return_value = mock_tmux

        await launch_with_animation(
            bot=bot,
            chat_id=-100123,
            thread_id=456,
            project=mock_project,
            thread=mock_thread,
            queue=queue,
            session_id="abc-123-def",  # NEW param
        )

        # Should send "claude --resume abc-123-def"
        mock_tmux.send.assert_called_with("claude --resume abc-123-def")


@pytest.mark.asyncio
async def test_launch_with_cwd_uses_custom_directory(mock_project, mock_thread):
    """When cwd provided, TmuxSession should use that cwd."""
    from codogram.telegram.launch_animation import launch_with_animation

    bot = AsyncMock()
    queue = AsyncMock()
    queue.send = AsyncMock(return_value=[123])

    with patch("codogram.telegram.launch_animation.TmuxSession") as MockTmux, \
         patch("codogram.telegram.launch_animation.project_manager"), \
         patch("codogram.telegram.launch_animation._start_monitoring"):

        mock_tmux = MagicMock()
        mock_tmux.exists.return_value = False
        mock_tmux.is_claude_ready.return_value = True
        MockTmux.return_value = mock_tmux

        await launch_with_animation(
            bot=bot,
            chat_id=-100123,
            thread_id=456,
            project=mock_project,
            thread=mock_thread,
            queue=queue,
            cwd="/home/user/project/.worktrees/feature-x",  # NEW param
        )

        # TmuxSession should be created with custom cwd
        MockTmux.assert_called_with(
            "test-project-feature-x",
            "/home/user/project/.worktrees/feature-x"
        )
