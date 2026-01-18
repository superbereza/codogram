"""Tests for WhisperService."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from codogram.services.whisper import WhisperService, TranscriptionResult


class TestWhisperService:
    """Tests for WhisperService."""

    def test_init_with_credentials(self):
        """Service initializes with API key and base URL."""
        service = WhisperService(
            api_key="test-key",
            base_url="https://custom.api.com/v1"
        )
        assert service.api_key == "test-key"
        assert service.base_url == "https://custom.api.com/v1"

    def test_init_default_base_url(self):
        """Service uses OpenAI default base URL."""
        service = WhisperService(api_key="test-key")
        assert service.base_url == "https://api.openai.com/v1"

    @pytest.mark.asyncio
    async def test_transcribe_success(self, tmp_path):
        """Successful transcription returns text."""
        service = WhisperService(api_key="test-key")

        # Create dummy audio file
        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake audio data")

        # Mock OpenAI client
        mock_response = MagicMock()
        mock_response.text = "Hello world"

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = await service.transcribe(audio_file)

        assert result.success is True
        assert result.text == "Hello world"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self, tmp_path):
        """Missing file returns error."""
        service = WhisperService(api_key="test-key")

        result = await service.transcribe(tmp_path / "nonexistent.ogg")

        assert result.success is False
        assert result.error == "file_not_found"

    @pytest.mark.asyncio
    async def test_transcribe_api_error_file_too_large(self, tmp_path):
        """API error about file size is mapped correctly."""
        service = WhisperService(api_key="test-key")

        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake audio data")

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            from openai import BadRequestError
            mock_api.side_effect = BadRequestError(
                message="Maximum content size limit exceeded",
                response=MagicMock(status_code=400),
                body={"error": {"message": "Maximum content size limit exceeded"}}
            )

            result = await service.transcribe(audio_file)

        assert result.success is False
        assert result.error == "file_too_large"

    @pytest.mark.asyncio
    async def test_transcribe_api_timeout(self, tmp_path):
        """Timeout is mapped correctly."""
        service = WhisperService(api_key="test-key")

        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake audio data")

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            import asyncio
            mock_api.side_effect = asyncio.TimeoutError()

            result = await service.transcribe(audio_file)

        assert result.success is False
        assert result.error == "timeout"
