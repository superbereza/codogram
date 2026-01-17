"""Tests for file input service."""
from pathlib import Path
from unittest.mock import MagicMock


class TestDomainTypes:
    def test_file_info_creation(self):
        from codogram.services.file_input import FileInfo

        info = FileInfo(file_id="abc123", extension="png", size=1000)

        assert info.file_id == "abc123"
        assert info.extension == "png"
        assert info.size == 1000

    def test_file_input_result_success(self):
        from codogram.services.file_input import FileInputResult

        result = FileInputResult(success=True, path=Path("/tmp/test.png"))

        assert result.success is True
        assert result.path == Path("/tmp/test.png")
        assert result.error is None

    def test_file_input_result_error(self):
        from codogram.services.file_input import FileInputResult

        result = FileInputResult(success=False, error="too_large")

        assert result.success is False
        assert result.path is None
        assert result.error == "too_large"


class TestExtractInfo:
    def test_extract_photo(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        photo = MagicMock()
        photo.file_id = "photo123"
        photo.file_size = 5000

        message = MagicMock()
        message.photo = [MagicMock(file_size=100), photo]  # Largest last
        message.document = None
        message.video = None
        message.audio = None
        message.voice = None

        result = service.extract_info(message)

        assert result is not None
        assert result.file_id == "photo123"
        assert result.extension == "jpg"
        assert result.size == 5000

    def test_extract_document_allowed(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        doc = MagicMock()
        doc.file_id = "doc456"
        doc.file_name = "report.pdf"
        doc.file_size = 10000

        message = MagicMock()
        message.photo = None
        message.document = doc
        message.video = None
        message.audio = None
        message.voice = None

        result = service.extract_info(message)

        assert result is not None
        assert result.file_id == "doc456"
        assert result.extension == "pdf"
        assert result.size == 10000

    def test_extract_document_blocked_extension(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        doc = MagicMock()
        doc.file_id = "exe123"
        doc.file_name = "virus.exe"
        doc.file_size = 1000

        message = MagicMock()
        message.photo = None
        message.document = doc
        message.video = None
        message.audio = None
        message.voice = None

        result = service.extract_info(message)

        assert result is None

    def test_extract_video_blocked(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        message = MagicMock()
        message.photo = None
        message.document = None
        message.video = MagicMock()
        message.audio = None
        message.voice = None

        result = service.extract_info(message)

        assert result is None

    def test_extract_audio_blocked(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        message = MagicMock()
        message.photo = None
        message.document = None
        message.video = None
        message.audio = MagicMock()
        message.voice = None

        result = service.extract_info(message)

        assert result is None

    def test_extract_voice_blocked(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        message = MagicMock()
        message.photo = None
        message.document = None
        message.video = None
        message.audio = None
        message.voice = MagicMock()

        result = service.extract_info(message)

        assert result is None