# tests/test_launch_animation_function.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from codogram.telegram.launch_animation import launch_with_animation, _start_monitoring


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=123))
    bot.delete_message = AsyncMock()
    return bot


@pytest.fixture
def mock_queue():
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value=[123])
    queue.send = AsyncMock(return_value=[123])
    return queue


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.project_name = "test-project"
    project.cwd = "/tmp/test"
    return project


@pytest.fixture
def mock_thread():
    thread = MagicMock()
    thread.thread_id = None
    thread.name = "main"
    thread.awaiting_new_session = False
    thread.launch_task = None
    thread.poller_task = None
    thread.get_tmux_session = MagicMock(return_value="claude-test-project")
    return thread


@pytest.mark.asyncio
async def test_launch_success_starts_poller(mock_bot, mock_queue, mock_project, mock_thread):
    """Successful launch starts poller only."""
    with patch('codogram.telegram.launch_animation.TmuxSession') as MockTmux, \
         patch('codogram.telegram.launch_animation.project_manager') as mock_pm, \
         patch('codogram.claude.poller.create_poller_task_for_thread', new_callable=AsyncMock) as mock_create_poller:

        # Setup tmux mock
        tmux_instance = MagicMock()
        tmux_instance.exists.return_value = True
        tmux_instance.is_claude_ready.return_value = True  # Ready immediately
        MockTmux.return_value = tmux_instance

        mock_create_poller.return_value = MagicMock()  # Return a mock task

        result = await launch_with_animation(
            bot=mock_bot,
            chat_id=123,
            thread_id=None,
            project=mock_project,
            thread=mock_thread,
            queue=mock_queue,
        )

        assert result is True
        assert mock_thread.poller_task is not None
        mock_pm._save.assert_called_once()


@pytest.mark.asyncio
async def test_launch_timeout_shows_error(mock_bot, mock_queue, mock_project, mock_thread):
    """After timeout, shows error message and returns False."""
    with patch('codogram.telegram.launch_animation.TmuxSession') as MockTmux, \
         patch('codogram.telegram.launch_animation.time') as mock_time:

        # Setup tmux mock - never ready
        tmux_instance = MagicMock()
        tmux_instance.exists.return_value = True
        tmux_instance.is_claude_ready.return_value = False
        MockTmux.return_value = tmux_instance

        # Simulate time passing - start at 0, then jump to 121 seconds
        mock_time.time.side_effect = [0, 0, 121]

        result = await launch_with_animation(
            bot=mock_bot,
            chat_id=123,
            thread_id=None,
            project=mock_project,
            thread=mock_thread,
            queue=mock_queue,
        )

        assert result is False
        # Check error message was sent via queue.send
        calls = mock_queue.send.call_args_list
        error_call = [c for c in calls if "Timeout" in str(c)]
        assert len(error_call) > 0


@pytest.mark.asyncio
async def test_launch_cleanup_on_error(mock_bot, mock_queue, mock_project, mock_thread):
    """Cleanup happens even on error."""
    mock_thread.awaiting_new_session = False
    mock_thread.launch_task = MagicMock()  # Simulate running task

    with patch('codogram.telegram.launch_animation.TmuxSession') as MockTmux:
        # Setup tmux mock to raise error
        tmux_instance = MagicMock()
        tmux_instance.exists.side_effect = Exception("Test error")
        MockTmux.return_value = tmux_instance

        result = await launch_with_animation(
            bot=mock_bot,
            chat_id=123,
            thread_id=None,
            project=mock_project,
            thread=mock_thread,
            queue=mock_queue,
        )

        assert result is False
        # Verify cleanup happened
        assert mock_thread.awaiting_new_session is False
        assert mock_thread.launch_task is None


@pytest.mark.asyncio
async def test_launch_creates_tmux_if_not_exists(mock_bot, mock_queue, mock_project, mock_thread):
    """Creates tmux session if it doesn't exist."""
    with patch('codogram.telegram.launch_animation.TmuxSession') as MockTmux, \
         patch('codogram.telegram.launch_animation.project_manager'), \
         patch('codogram.claude.poller.create_poller_task_for_thread', new_callable=AsyncMock) as mock_create_poller:

        tmux_instance = MagicMock()
        tmux_instance.exists.return_value = False  # Doesn't exist
        tmux_instance.is_claude_ready.return_value = True
        MockTmux.return_value = tmux_instance

        mock_create_poller.return_value = MagicMock()

        await launch_with_animation(
            bot=mock_bot,
            chat_id=123,
            thread_id=None,
            project=mock_project,
            thread=mock_thread,
            queue=mock_queue,
        )

        tmux_instance.create.assert_called_once()
        tmux_instance.send.assert_called_once_with("claude")


@pytest.mark.asyncio
async def test_launch_sends_claude_command(mock_bot, mock_queue, mock_project, mock_thread):
    """Sends 'claude' command to tmux."""
    with patch('codogram.telegram.launch_animation.TmuxSession') as MockTmux, \
         patch('codogram.telegram.launch_animation.project_manager'), \
         patch('codogram.claude.poller.create_poller_task_for_thread', new_callable=AsyncMock) as mock_create_poller:

        tmux_instance = MagicMock()
        tmux_instance.exists.return_value = True
        tmux_instance.is_claude_ready.return_value = True
        MockTmux.return_value = tmux_instance

        mock_create_poller.return_value = MagicMock()

        await launch_with_animation(
            bot=mock_bot,
            chat_id=123,
            thread_id=None,
            project=mock_project,
            thread=mock_thread,
            queue=mock_queue,
        )

        tmux_instance.send.assert_called_once_with("claude")


@pytest.mark.asyncio
async def test_start_monitoring_creates_poller(mock_bot, mock_queue, mock_project, mock_thread):
    """_start_monitoring creates poller task when none exists."""
    with patch('codogram.claude.poller.create_poller_task_for_thread', new_callable=AsyncMock) as mock_create_poller:
        mock_task = MagicMock()
        mock_create_poller.return_value = mock_task

        mock_thread.poller_task = None

        await _start_monitoring(mock_bot, mock_project, mock_thread, mock_queue)

        mock_create_poller.assert_called_once_with(mock_bot, mock_project, mock_thread, mock_queue)
        assert mock_thread.poller_task == mock_task


@pytest.mark.asyncio
async def test_start_monitoring_skips_if_poller_running(mock_bot, mock_queue, mock_project, mock_thread):
    """_start_monitoring skips if poller is already running."""
    with patch('codogram.claude.poller.create_poller_task_for_thread', new_callable=AsyncMock) as mock_create_poller:
        existing_task = MagicMock()
        existing_task.done.return_value = False  # Still running
        mock_thread.poller_task = existing_task

        await _start_monitoring(mock_bot, mock_project, mock_thread, mock_queue)

        mock_create_poller.assert_not_called()
        assert mock_thread.poller_task == existing_task


@pytest.mark.asyncio
async def test_start_monitoring_restarts_if_poller_done(mock_bot, mock_queue, mock_project, mock_thread):
    """_start_monitoring restarts poller if previous task is done."""
    with patch('codogram.claude.poller.create_poller_task_for_thread', new_callable=AsyncMock) as mock_create_poller:
        old_task = MagicMock()
        old_task.done.return_value = True  # Finished
        mock_thread.poller_task = old_task

        new_task = MagicMock()
        mock_create_poller.return_value = new_task

        await _start_monitoring(mock_bot, mock_project, mock_thread, mock_queue)

        mock_create_poller.assert_called_once()
        assert mock_thread.poller_task == new_task


@pytest.mark.asyncio
async def test_launch_fails_if_cwd_is_none(mock_bot, mock_queue, mock_project, mock_thread):
    """Launch returns False and sends error if project.cwd is None."""
    mock_project.cwd = None

    result = await launch_with_animation(
        bot=mock_bot,
        chat_id=123,
        thread_id=None,
        project=mock_project,
        thread=mock_thread,
        queue=mock_queue,
    )

    assert result is False
    # Check error message was sent
    mock_queue.send.assert_called_once()
    call_args = mock_queue.send.call_args
    assert "cwd not set" in call_args[0][1]
