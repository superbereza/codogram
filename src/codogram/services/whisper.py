"""Whisper transcription service."""
from dataclasses import dataclass
from pathlib import Path
import asyncio

from openai import AsyncOpenAI, BadRequestError, APITimeoutError, APIError

from ..logging_config import logger


@dataclass
class TranscriptionResult:
    """Result of transcription attempt."""
    success: bool
    text: str | None = None
    error: str | None = None  # file_not_found, file_too_large, format, timeout, no_speech, api_error


class WhisperService:
    """Service for audio transcription via OpenAI Whisper API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 60
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self._client

    async def _call_api(self, file_path: Path):
        """Call Whisper API. Separated for testing."""
        client = self._get_client()
        with open(file_path, "rb") as audio_file:
            return await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

    async def transcribe(self, file_path: Path) -> TranscriptionResult:
        """Transcribe audio file.

        Args:
            file_path: Path to audio file (ogg, mp3, m4a, wav, mp4)

        Returns:
            TranscriptionResult with success/text or error code
        """
        # Check file exists
        if not file_path.exists():
            return TranscriptionResult(success=False, error="file_not_found")

        try:
            logger.info(f"Transcribing {file_path.name} ({file_path.stat().st_size} bytes)")

            response = await self._call_api(file_path)
            text = response.text.strip() if response.text else ""

            if not text:
                return TranscriptionResult(success=False, error="no_speech")

            logger.info(f"Transcription complete: {len(text)} chars")
            return TranscriptionResult(success=True, text=text)

        except BadRequestError as e:
            error_msg = str(e).lower()
            if "size" in error_msg or "large" in error_msg or "limit" in error_msg:
                return TranscriptionResult(success=False, error="file_too_large")
            if "format" in error_msg or "codec" in error_msg:
                return TranscriptionResult(success=False, error="format")
            logger.error(f"Whisper BadRequest: {e}")
            return TranscriptionResult(success=False, error="api_error")

        except (APITimeoutError, asyncio.TimeoutError):
            return TranscriptionResult(success=False, error="timeout")

        except APIError as e:
            logger.error(f"Whisper API error: {e}")
            return TranscriptionResult(success=False, error="api_error")

        except Exception as e:
            logger.exception(f"Whisper unexpected error: {e}")
            return TranscriptionResult(success=False, error="api_error")
