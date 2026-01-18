"""Tests for FileInputService audio handling."""
from unittest.mock import MagicMock

from codogram.services.file_input import FileInputService, AudioFileInfo


class TestExtractAudioInfo:
    """Tests for extract_audio_info method."""

    def setup_method(self):
        self.service = FileInputService()

    def test_voice_message(self):
        """Extracts info from voice message."""
        message = MagicMock()
        message.voice = MagicMock(
            file_id="voice123",
            file_size=5000,
            duration=10
        )
        message.audio = None
        message.video_note = None

        result = self.service.extract_audio_info(message)

        assert result is not None
        assert result.file_id == "voice123"
        assert result.extension == "ogg"
        assert result.size == 5000
        assert result.duration == 10

    def test_audio_file_with_name(self):
        """Extracts info from audio file with filename."""
        message = MagicMock()
        message.voice = None
        message.audio = MagicMock(
            file_id="audio456",
            file_name="song.mp3",
            file_size=1000000,
            duration=180
        )
        message.video_note = None

        result = self.service.extract_audio_info(message)

        assert result is not None
        assert result.file_id == "audio456"
        assert result.extension == "mp3"
        assert result.size == 1000000

    def test_audio_file_no_name(self):
        """Audio without filename defaults to mp3."""
        message = MagicMock()
        message.voice = None
        message.audio = MagicMock(
            file_id="audio789",
            file_name=None,
            file_size=50000,
            duration=30
        )
        message.video_note = None

        result = self.service.extract_audio_info(message)

        assert result is not None
        assert result.extension == "mp3"

    def test_video_note(self):
        """Extracts info from video note (round video)."""
        message = MagicMock()
        message.voice = None
        message.audio = None
        message.video_note = MagicMock(
            file_id="videonote123",
            file_size=200000,
            duration=15
        )

        result = self.service.extract_audio_info(message)

        assert result is not None
        assert result.file_id == "videonote123"
        assert result.extension == "mp4"
        assert result.duration == 15

    def test_no_audio_content(self):
        """Returns None for non-audio message."""
        message = MagicMock()
        message.voice = None
        message.audio = None
        message.video_note = None

        result = self.service.extract_audio_info(message)

        assert result is None
