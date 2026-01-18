# Whisper Transcription for Audio/Video Messages

## Overview

Add support for voice messages, audio files, and video notes via OpenAI Whisper API transcription.

**User flow:**
```
User: [sends voice message]
Bot: `[~]` Transcribing...
Bot: `[v]` «привет как дела» → Claude
Claude: [responds in chat]
```

**Error flow:**
```
User: [sends huge file]
Bot: `[~]` Transcribing...
Bot: `[x]` Transcription failed: file too large
```

## Supported Media Types

- Voice messages (`.ogg`)
- Audio files (`.mp3`, `.m4a`, `.wav`, etc.)
- Video notes / круглые видео (`.mp4`)

## Architecture

### New Files

```
src/codogram/
├── services/
│   └── whisper.py          # WhisperService - transcription logic
├── handlers/
│   └── audio.py            # Audio message handler
```

### Modified Files

```
src/codogram/
├── config.py               # Add OPENAI_API_KEY, OPENAI_BASE_URL
├── strings.py              # Add AUDIO_* strings
├── services/file_input.py  # Extend for audio file saving
├── handlers/messages.py    # Remove audio block
├── main.py                 # Register audio router
```

## Components

### WhisperService

```python
# services/whisper.py

@dataclass
class TranscriptionResult:
    success: bool
    text: str | None = None
    error: str | None = None  # "file_too_large" | "api_error" | "timeout" | etc.

class WhisperService:
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        ...

    async def transcribe(self, file_path: Path) -> TranscriptionResult:
        """Transcribe audio file via Whisper API."""
        ...
```

**Error mapping:**
| API Error | Internal Code | User String |
|-----------|---------------|-------------|
| file too large | `file_too_large` | `AUDIO_ERR_TOO_LARGE` |
| invalid format | `format` | `AUDIO_ERR_FORMAT` |
| timeout/network | `timeout` | `AUDIO_ERR_TIMEOUT` |
| no speech | `no_speech` | `AUDIO_ERR_NO_SPEECH` |
| other | `api_error` | `AUDIO_ERR_GENERIC` |

### Audio Handler

```python
# handlers/audio.py

@router.message(F.content_type.in_({ContentType.VOICE, ContentType.AUDIO, ContentType.VIDEO_NOTE}))
async def on_audio(message: Message, telegram_queue: TelegramQueue):
    # 1. Check if whisper configured
    # 2. Send "Transcribing..." message
    # 3. Download file from Telegram
    # 4. Save to tmp/input-files/{thread}/
    # 5. Call WhisperService.transcribe()
    # 6. On success: show «text» → Claude, route to tmux
    # 7. On error: show error message
```

### FileInputService Extension

```python
# New in services/file_input.py

AUDIO_EXTENSIONS = {"ogg", "mp3", "m4a", "wav", "mp4"}

@dataclass
class AudioFileInfo:
    file_id: str
    extension: str
    size: int
    duration: int | None = None

def extract_audio_info(self, message) -> AudioFileInfo | None:
    """Extract info from voice/audio/video_note."""
    ...
```

**File path pattern:** `{cwd}/tmp/input-files/{thread_name}/{datetime}-{thread_id}-user_{user_id}.{ext}`

## Strings

```python
# strings.py additions

# --- Audio/Whisper ---

AUDIO_TRANSCRIBING = f"{STATUS_PENDING} Transcribing..."
AUDIO_SENT = f"{STATUS_OK} «{{text}}» → Claude"

# Errors
AUDIO_ERR_TOO_LARGE = f"{STATUS_ERR} Transcription failed: file too large"
AUDIO_ERR_FORMAT = f"{STATUS_ERR} Transcription failed: unsupported format"
AUDIO_ERR_TIMEOUT = f"{STATUS_ERR} Transcription failed: timeout, try again"
AUDIO_ERR_GENERIC = f"{STATUS_ERR} Transcription failed: {{error}}"
AUDIO_ERR_NO_SPEECH = f"{STATUS_ERR} No speech detected"
AUDIO_ERR_NOT_CONFIGURED = f"{STATUS_ERR} Whisper not configured (missing OPENAI_API_KEY)"
```

**Remove:** `FILE_AUDIO_VIDEO_NOT_SUPPORTED`

## Config

```python
# config.py additions

OPENAI_API_KEY: str | None = None
OPENAI_BASE_URL: str = "https://api.openai.com/v1"
```

**.env.example:**
```bash
# Whisper (audio transcription)
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # optional
```

**Graceful degradation:** If `OPENAI_API_KEY` not set, audio handler replies with `AUDIO_ERR_NOT_CONFIGURED`. Bot continues working for text/images.

## Dependencies

Add to `pyproject.toml`:
```toml
openai = "^1.0"
```

## Reference Implementation

Based on `/home/superbereza/dev/bz-merch-assistant/packages/ai_bot_core/ai_bot_core/services/whisper.py`

Simplified version without:
- Langfuse observability
- MinIO storage
- Duration limits (trust API)
