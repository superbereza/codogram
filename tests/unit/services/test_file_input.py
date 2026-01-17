"""Tests for file input service."""
from pathlib import Path


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
