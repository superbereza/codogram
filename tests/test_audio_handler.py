"""Tests for audio message handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAudioHandler:
    """Tests for audio message handling."""

    @pytest.mark.asyncio
    async def test_no_api_key_configured(self):
        """Returns error when OPENAI_API_KEY not set."""
        from codogram.handlers.audio import _handle_audio_message

        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.chat.type = "private"
        message.from_user.id = 456
        message.message_thread_id = None

        telegram_queue = AsyncMock()

        with patch('codogram.handlers.audio.settings') as mock_settings:
            mock_settings.openai_api_key = None

            await _handle_audio_message(message, telegram_queue)

        # Should send error about missing config
        telegram_queue.reply.assert_called_once()
        call_args = telegram_queue.reply.call_args
        assert "not configured" in call_args[0][1].lower() or "OPENAI_API_KEY" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_no_project_registered(self):
        """Silent return when no project for chat."""
        from codogram.handlers.audio import _handle_audio_message

        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.chat.type = "private"
        message.from_user.id = 456
        message.message_thread_id = None

        telegram_queue = AsyncMock()

        with patch('codogram.handlers.audio.settings') as mock_settings, \
             patch('codogram.handlers.audio._message_router') as mock_router:
            mock_settings.openai_api_key = "test-key"

            from codogram.services.message_router import RouteAction
            mock_router.route.return_value = MagicMock(action=RouteAction.NO_PROJECT)

            await _handle_audio_message(message, telegram_queue)

        # Should not send any message (silent)
        telegram_queue.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_thread_silent(self):
        """Silent return for pending threads."""
        from codogram.handlers.audio import _handle_audio_message

        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.chat.type = "private"
        message.from_user.id = 456
        message.message_thread_id = None

        telegram_queue = AsyncMock()

        with patch('codogram.handlers.audio.settings') as mock_settings, \
             patch('codogram.handlers.audio._message_router') as mock_router:
            mock_settings.openai_api_key = "test-key"

            from codogram.services.message_router import RouteAction
            mock_router.route.return_value = MagicMock(action=RouteAction.SKIP_PENDING)

            await _handle_audio_message(message, telegram_queue)

        # Should not send any message (silent)
        telegram_queue.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_audio_content(self):
        """Returns early if no audio content extracted."""
        from codogram.handlers.audio import _handle_audio_message

        message = MagicMock()
        message.voice = None
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.chat.type = "private"
        message.from_user.id = 456
        message.message_thread_id = None

        telegram_queue = AsyncMock()

        with patch('codogram.handlers.audio.settings') as mock_settings, \
             patch('codogram.handlers.audio._message_router') as mock_router, \
             patch('codogram.handlers.audio._file_input') as mock_file_input:
            mock_settings.openai_api_key = "test-key"

            from codogram.services.message_router import RouteAction
            mock_router.route.return_value = MagicMock(
                action=RouteAction.SEND_TO_TMUX,
                cwd="/tmp",
                thread=MagicMock(name="main")
            )

            mock_file_input.extract_audio_info.return_value = None

            await _handle_audio_message(message, telegram_queue)

        # Should not send any message
        telegram_queue.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_transcription_flow(self, tmp_path):
        """Full flow: download -> save -> transcribe -> send to Claude."""
        from codogram.handlers.audio import _handle_audio_message

        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.chat.type = "private"
        message.from_user.id = 456
        message.message_thread_id = None
        message.bot = AsyncMock()
        message.bot.get_file = AsyncMock(return_value=MagicMock(file_path="voice/file.ogg"))
        message.bot.download = AsyncMock()

        telegram_queue = AsyncMock()
        # reply returns a message that can be edited
        status_msg = MagicMock()
        telegram_queue.reply = AsyncMock(return_value=status_msg)

        # Mock all dependencies
        with patch('codogram.handlers.audio.settings') as mock_settings, \
             patch('codogram.handlers.audio._message_router') as mock_router, \
             patch('codogram.handlers.audio._file_input') as mock_file_input, \
             patch('codogram.handlers.audio.WhisperService') as MockWhisper:

            mock_settings.openai_api_key = "test-key"
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.whisper_timeout = 60

            # Route result
            from codogram.services.message_router import RouteAction, RouteResult
            mock_thread = MagicMock(name="main")
            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=MagicMock(cwd="/tmp/project"),
                thread=mock_thread,
                tmux_name="tmux-session",
                cwd="/tmp/project"
            )
            mock_router.send_to_tmux.return_value = True

            # File input
            from codogram.services.file_input import AudioFileInfo
            mock_file_input.extract_audio_info.return_value = AudioFileInfo(
                file_id="v1", extension="ogg", size=1000, duration=5
            )
            mock_file_input._build_path.return_value = tmp_path / "audio.ogg"

            # Whisper
            from codogram.services.whisper import TranscriptionResult
            mock_whisper_instance = AsyncMock()
            mock_whisper_instance.transcribe.return_value = TranscriptionResult(
                success=True, text="Hello world"
            )
            MockWhisper.return_value = mock_whisper_instance

            await _handle_audio_message(message, telegram_queue)

        # Should send "Transcribing..." then edit with result
        telegram_queue.reply.assert_called_once()
        telegram_queue.edit.assert_called_once()

        # Should send to tmux
        mock_router.send_to_tmux.assert_called_once()
        # Verify text was passed
        call_args = mock_router.send_to_tmux.call_args
        assert call_args[0][1] == "Hello world"

    @pytest.mark.asyncio
    async def test_transcription_error_shows_message(self, tmp_path):
        """Transcription error is shown to user."""
        from codogram.handlers.audio import _handle_audio_message

        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.chat.type = "private"
        message.from_user.id = 456
        message.message_thread_id = None
        message.bot = AsyncMock()
        message.bot.get_file = AsyncMock(return_value=MagicMock(file_path="voice/file.ogg"))
        message.bot.download = AsyncMock()

        telegram_queue = AsyncMock()
        status_msg = MagicMock()
        telegram_queue.reply = AsyncMock(return_value=status_msg)

        with patch('codogram.handlers.audio.settings') as mock_settings, \
             patch('codogram.handlers.audio._message_router') as mock_router, \
             patch('codogram.handlers.audio._file_input') as mock_file_input, \
             patch('codogram.handlers.audio.WhisperService') as MockWhisper:

            mock_settings.openai_api_key = "test-key"
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.whisper_timeout = 60

            from codogram.services.message_router import RouteAction, RouteResult
            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=MagicMock(cwd="/tmp/project"),
                thread=MagicMock(name="main"),
                tmux_name="tmux-session",
                cwd="/tmp/project"
            )

            from codogram.services.file_input import AudioFileInfo
            mock_file_input.extract_audio_info.return_value = AudioFileInfo(
                file_id="v1", extension="ogg", size=1000, duration=5
            )
            mock_file_input._build_path.return_value = tmp_path / "audio.ogg"

            from codogram.services.whisper import TranscriptionResult
            mock_whisper_instance = AsyncMock()
            mock_whisper_instance.transcribe.return_value = TranscriptionResult(
                success=False, error="timeout"
            )
            MockWhisper.return_value = mock_whisper_instance

            await _handle_audio_message(message, telegram_queue)

        # Should edit status with error message
        telegram_queue.edit.assert_called_once()
        edit_call = telegram_queue.edit.call_args
        assert "timeout" in edit_call[0][1].lower()

        # Should NOT send to tmux on error
        mock_router.send_to_tmux.assert_not_called()

    @pytest.mark.asyncio
    async def test_forum_thread_handling(self, tmp_path):
        """Handles forum thread_id correctly."""
        from codogram.handlers.audio import _handle_audio_message

        message = MagicMock()
        message.voice = MagicMock(file_id="v1", file_size=1000, duration=5)
        message.audio = None
        message.video_note = None
        message.chat.id = 123
        message.chat.type = "supergroup"
        message.chat.is_forum = True
        message.from_user.id = 456
        message.message_thread_id = 789  # Forum topic ID
        message.bot = AsyncMock()
        message.bot.get_file = AsyncMock(return_value=MagicMock(file_path="voice/file.ogg"))
        message.bot.download = AsyncMock()

        telegram_queue = AsyncMock()
        status_msg = MagicMock()
        telegram_queue.reply = AsyncMock(return_value=status_msg)

        with patch('codogram.handlers.audio.settings') as mock_settings, \
             patch('codogram.handlers.audio._message_router') as mock_router, \
             patch('codogram.handlers.audio._file_input') as mock_file_input, \
             patch('codogram.handlers.audio.WhisperService') as MockWhisper:

            mock_settings.openai_api_key = "test-key"
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.whisper_timeout = 60

            from codogram.services.message_router import RouteAction, RouteResult
            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=MagicMock(cwd="/tmp/project"),
                thread=MagicMock(name="feature"),
                tmux_name="tmux-session",
                cwd="/tmp/project"
            )
            mock_router.send_to_tmux.return_value = True

            from codogram.services.file_input import AudioFileInfo
            mock_file_input.extract_audio_info.return_value = AudioFileInfo(
                file_id="v1", extension="ogg", size=1000, duration=5
            )
            mock_file_input._build_path.return_value = tmp_path / "audio.ogg"

            from codogram.services.whisper import TranscriptionResult
            mock_whisper_instance = AsyncMock()
            mock_whisper_instance.transcribe.return_value = TranscriptionResult(
                success=True, text="Test message"
            )
            MockWhisper.return_value = mock_whisper_instance

            await _handle_audio_message(message, telegram_queue)

        # Router should be called with thread_id=789
        mock_router.route.assert_called_once_with(123, 789, "")
