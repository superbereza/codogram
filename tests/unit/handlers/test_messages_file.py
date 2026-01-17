"""Tests for file message handling."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path


class TestFileMessageHandler:
    @pytest.mark.asyncio
    async def test_photo_sent_to_tmux(self, tmp_path):
        """Photo message should be downloaded and sent to tmux."""
        from codogram.handlers.messages import on_message
        from codogram.services.message_router import RouteAction, RouteResult
        from codogram.services.file_input import FileInfo, FileInputResult

        # Mock photo
        photo = MagicMock()
        photo.file_id = "photo123"
        photo.file_size = 1000

        # Mock message
        message = MagicMock()
        message.text = None
        message.caption = "Check this"
        message.photo = [photo]
        message.document = None
        message.video = None
        message.audio = None
        message.voice = None
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = 1328
        message.from_user = MagicMock(id=456)
        message.bot = MagicMock()
        message.bot.download = AsyncMock()

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        mock_project = MagicMock()
        mock_project.cwd = str(tmp_path)
        mock_thread = MagicMock()
        mock_thread.name = "celestial"
        mock_thread.session_id = "sess123"

        with patch("codogram.handlers.messages._message_router") as mock_router, \
             patch("codogram.handlers.messages._file_input") as mock_file_svc, \
             patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):

            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=mock_project,
                thread=mock_thread,
                tmux_name="claude-test",
                cwd=str(tmp_path)
            )

            mock_file_svc.extract_info.return_value = FileInfo(
                file_id="photo123", extension="jpg", size=1000
            )
            mock_file_svc.save_file = AsyncMock(return_value=FileInputResult(
                success=True, path=tmp_path / "test.jpg"
            ))
            mock_file_svc.format_message.return_value = "Check this\n\n📎 ./test.jpg"

            mock_router.send_to_tmux.return_value = True

            await on_message(message, telegram_queue)

            # Verify service was called with callback
            mock_file_svc.save_file.assert_called_once()
            call_kwargs = mock_file_svc.save_file.call_args[1]
            assert call_kwargs["thread_name"] == "celestial"
            assert "download_fn" in call_kwargs

            # Verify sent to tmux
            mock_router.send_to_tmux.assert_called_once()

    @pytest.mark.asyncio
    async def test_video_rejected(self):
        """Video messages should be rejected with friendly message."""
        from codogram.handlers.messages import on_message

        message = MagicMock()
        message.text = None
        message.photo = None
        message.document = None
        message.video = MagicMock()
        message.audio = None
        message.voice = None
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = None
        message.from_user = MagicMock(id=123)

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        with patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):
            await on_message(message, telegram_queue)

            telegram_queue.reply.assert_called_once()
            reply_text = telegram_queue.reply.call_args[0][1]
            assert "video" in reply_text.lower() or "audio" in reply_text.lower()

    @pytest.mark.asyncio
    async def test_audio_rejected(self):
        """Audio messages should be rejected with friendly message."""
        from codogram.handlers.messages import on_message

        message = MagicMock()
        message.text = None
        message.photo = None
        message.document = None
        message.video = None
        message.audio = MagicMock()
        message.voice = None
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = None
        message.from_user = MagicMock(id=123)

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        with patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):
            await on_message(message, telegram_queue)

            telegram_queue.reply.assert_called_once()
            reply_text = telegram_queue.reply.call_args[0][1]
            assert "whisper" in reply_text.lower()

    @pytest.mark.asyncio
    async def test_voice_rejected(self):
        """Voice messages should be rejected with friendly message."""
        from codogram.handlers.messages import on_message

        message = MagicMock()
        message.text = None
        message.photo = None
        message.document = None
        message.video = None
        message.audio = None
        message.voice = MagicMock()
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = None
        message.from_user = MagicMock(id=123)

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        with patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):
            await on_message(message, telegram_queue)

            telegram_queue.reply.assert_called_once()
            reply_text = telegram_queue.reply.call_args[0][1]
            assert "whisper" in reply_text.lower()

    @pytest.mark.asyncio
    async def test_file_download_error_shows_message(self, tmp_path):
        """Download failure should show user-friendly error."""
        from codogram.handlers.messages import on_message
        from codogram.services.message_router import RouteAction, RouteResult
        from codogram.services.file_input import FileInfo, FileInputResult

        photo = MagicMock()
        photo.file_id = "photo123"
        photo.file_size = 1000

        message = MagicMock()
        message.text = None
        message.caption = None
        message.photo = [photo]
        message.document = None
        message.video = None
        message.audio = None
        message.voice = None
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = None
        message.from_user = MagicMock(id=456)
        message.bot = MagicMock()
        message.bot.download = AsyncMock()

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        mock_project = MagicMock()
        mock_project.cwd = str(tmp_path)
        mock_thread = MagicMock()
        mock_thread.name = "main"

        with patch("codogram.handlers.messages._message_router") as mock_router, \
             patch("codogram.handlers.messages._file_input") as mock_file_svc, \
             patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):

            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=mock_project,
                thread=mock_thread,
                tmux_name="claude-test",
                cwd=str(tmp_path)
            )

            mock_file_svc.extract_info.return_value = FileInfo(
                file_id="photo123", extension="jpg", size=1000
            )
            # Simulate download failure
            mock_file_svc.save_file = AsyncMock(return_value=FileInputResult(
                success=False, error="download_failed"
            ))

            await on_message(message, telegram_queue)

            # Should show error to user
            telegram_queue.reply.assert_called_once()
            reply_text = telegram_queue.reply.call_args[0][1]
            assert "download failed" in reply_text.lower()

    @pytest.mark.asyncio
    async def test_file_too_large_shows_message(self, tmp_path):
        """File over 20MB should show size error."""
        from codogram.handlers.messages import on_message
        from codogram.services.message_router import RouteAction, RouteResult
        from codogram.services.file_input import FileInfo, FileInputResult

        photo = MagicMock()
        photo.file_id = "photo123"
        photo.file_size = 25 * 1024 * 1024  # 25MB

        message = MagicMock()
        message.text = None
        message.caption = None
        message.photo = [photo]
        message.document = None
        message.video = None
        message.audio = None
        message.voice = None
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = None
        message.from_user = MagicMock(id=456)
        message.bot = MagicMock()

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        mock_project = MagicMock()
        mock_project.cwd = str(tmp_path)
        mock_thread = MagicMock()
        mock_thread.name = "main"

        with patch("codogram.handlers.messages._message_router") as mock_router, \
             patch("codogram.handlers.messages._file_input") as mock_file_svc, \
             patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):

            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=mock_project,
                thread=mock_thread,
                tmux_name="claude-test",
                cwd=str(tmp_path)
            )

            mock_file_svc.extract_info.return_value = FileInfo(
                file_id="photo123", extension="jpg", size=25 * 1024 * 1024
            )
            # Simulate size validation failure
            mock_file_svc.save_file = AsyncMock(return_value=FileInputResult(
                success=False, error="too_large"
            ))

            await on_message(message, telegram_queue)

            # Should show size error
            telegram_queue.reply.assert_called_once()
            reply_text = telegram_queue.reply.call_args[0][1]
            assert "20mb" in reply_text.lower()

    @pytest.mark.asyncio
    async def test_unsupported_document_rejected(self, tmp_path):
        """Document with unsupported extension should be rejected."""
        from codogram.handlers.messages import on_message
        from codogram.services.message_router import RouteAction, RouteResult

        doc = MagicMock()
        doc.file_id = "doc123"
        doc.file_name = "archive.zip"
        doc.file_size = 1000

        message = MagicMock()
        message.text = None
        message.caption = None
        message.photo = None
        message.document = doc
        message.video = None
        message.audio = None
        message.voice = None
        message.chat = MagicMock(id=-100123)
        message.message_thread_id = None
        message.from_user = MagicMock(id=456)
        message.bot = MagicMock()

        telegram_queue = MagicMock()
        telegram_queue.reply = AsyncMock()

        mock_project = MagicMock()
        mock_project.cwd = str(tmp_path)
        mock_thread = MagicMock()
        mock_thread.name = "main"

        with patch("codogram.handlers.messages._message_router") as mock_router, \
             patch("codogram.handlers.messages._file_input") as mock_file_svc, \
             patch("codogram.handlers.messages.handle_name_input", new_callable=AsyncMock, return_value=False):

            mock_router.route.return_value = RouteResult(
                action=RouteAction.SEND_TO_TMUX,
                project=mock_project,
                thread=mock_thread,
                tmux_name="claude-test",
                cwd=str(tmp_path)
            )

            # extract_info returns None for unsupported types
            mock_file_svc.extract_info.return_value = None

            await on_message(message, telegram_queue)

            # Should show file type not supported
            telegram_queue.reply.assert_called_once()
            reply_text = telegram_queue.reply.call_args[0][1]
            assert "not supported" in reply_text.lower()
