"""Tests for file input service."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
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


class TestSaveFile:
    @pytest.mark.asyncio
    @freeze_time("2026-01-17 04:35:12")
    async def test_save_file_success(self, tmp_path):
        from codogram.services.file_input import FileInputService, FileInfo

        service = FileInputService()
        file_info = FileInfo(file_id="abc123", extension="png", size=1000)

        async def mock_download(file_id, destination):
            Path(destination).write_bytes(b"fake image data")

        result = await service.save_file(
            file_info=file_info,
            cwd=str(tmp_path),
            thread_name="celestial",
            thread_id=1328,
            user_id=456,
            download_fn=mock_download
        )

        assert result.success is True
        assert result.path is not None
        assert result.path.exists()
        assert result.path.read_bytes() == b"fake image data"
        assert "celestial" in str(result.path)

    @pytest.mark.asyncio
    async def test_save_file_too_large(self, tmp_path):
        from codogram.services.file_input import FileInputService, FileInfo

        service = FileInputService()
        file_info = FileInfo(
            file_id="abc123",
            extension="png",
            size=25 * 1024 * 1024  # 25MB > 20MB limit
        )

        async def mock_download(file_id, destination):
            pass

        result = await service.save_file(
            file_info=file_info,
            cwd=str(tmp_path),
            thread_name="main",
            thread_id=None,
            user_id=123,
            download_fn=mock_download
        )

        assert result.success is False
        assert result.error == "too_large"

    @pytest.mark.asyncio
    async def test_save_file_download_fails(self, tmp_path):
        from codogram.services.file_input import FileInputService, FileInfo

        service = FileInputService()
        file_info = FileInfo(file_id="abc123", extension="png", size=1000)

        async def failing_download(file_id, destination):
            raise Exception("Network error")

        result = await service.save_file(
            file_info=file_info,
            cwd=str(tmp_path),
            thread_name="main",
            thread_id=None,
            user_id=123,
            download_fn=failing_download
        )

        assert result.success is False
        assert result.error == "download_failed"


class TestFormatMessage:
    def test_format_single_file_no_caption(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        msg = service.format_message(
            caption=None,
            paths=[Path("/project/tmp/input-files/main/test.png")],
            cwd="/project"
        )

        assert msg == "See file: ./tmp/input-files/main/test.png"

    def test_format_single_file_with_caption(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        msg = service.format_message(
            caption="Check this mockup",
            paths=[Path("/project/tmp/input-files/celestial/design.png")],
            cwd="/project"
        )

        assert msg == "Check this mockup\n\nSee file: ./tmp/input-files/celestial/design.png"

    def test_format_multiple_files(self):
        from codogram.services.file_input import FileInputService

        service = FileInputService()
        msg = service.format_message(
            caption="Review these",
            paths=[
                Path("/project/tmp/input-files/main/a.png"),
                Path("/project/tmp/input-files/main/b.png"),
            ],
            cwd="/project"
        )

        expected = "Review these\n\nSee file: ./tmp/input-files/main/a.png\nSee file: ./tmp/input-files/main/b.png"
        assert msg == expected