"""Tests for file input service."""
from pathlib import Path
from unittest.mock import MagicMock

from freezegun import freeze_time


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


class TestBuildPath:
    @freeze_time("2026-01-17 04:35:12")
    def test_build_path_basic(self, tmp_path):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        path = service._build_path(
            cwd=str(tmp_path),
            thread_name="celestial",
            thread_id=1328,
            user_id=456,
            extension="png"
        )

        assert path.parent.exists()
        assert "celestial" in str(path)
        assert "20260117-043512" in str(path)
        assert "thread_1328" in str(path)
        assert "user_456" in str(path)
        assert path.suffix == ".png"

    @freeze_time("2026-01-17 04:35:12")
    def test_build_path_main_thread(self, tmp_path):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        path = service._build_path(
            cwd=str(tmp_path),
            thread_name="main",
            thread_id=None,
            user_id=123,
            extension="jpg"
        )

        assert "main" in str(path)
        assert "thread_main" in str(path)

    def test_build_path_traversal_blocked(self, tmp_path):
        from codogram.services.file_input import FileInputService

        service = FileInputService()

        try:
            service._build_path(
                cwd=str(tmp_path),
                thread_name="../../../etc",
                thread_id=1,
                user_id=1,
                extension="txt"
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "outside" in str(e).lower()