# Image and File Input Support

## Problem

Users can only send text messages to Claude through Telegram. Need to support sending images and files that Claude Code can analyze.

## Solution

Download files from Telegram, save to project folder, send file path to tmux. Claude Code reads files via its Read tool.

## Architecture

### Flow

```
User sends photo/file in Telegram
        ↓
Handler extracts FileInfo, creates download callback
        ↓
Service validates, builds path, calls callback to download
        ↓
Save to {cwd}/tmp/input-files/{thread.name}/
        ↓
Send to tmux: "{caption}\n\n📎 ./tmp/input-files/..."
        ↓
Claude Code reads file with Read tool
```

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Handler (handlers/messages.py)                              │
│                                                             │
│  - Extracts FileInfo from message                           │
│  - Creates download callback (closure over bot)             │
│  - Calls service.save_file(..., download_fn)                │
│  - Handles errors, replies to user                          │
│  - Sends formatted message to tmux                          │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Service (services/file_input.py)                            │
│                                                             │
│  - Validates extension and size                             │
│  - Builds safe path with traversal protection               │
│  - Calls download_fn(file_id, path) - doesn't know aiogram  │
│  - Returns FileInputResult with success/error/path          │
│  - Formats message for tmux                                 │
└─────────────────────────────────────────────────────────────┘
```

**Key principle:** Service receives `download_fn: Callable` instead of `message.bot`. This way service doesn't know about aiogram but can still orchestrate the full flow.

### File Storage

**Directory structure:**
```
{project_cwd}/tmp/input-files/{thread.name}/{filename}
```

Examples:
```
/project/tmp/input-files/main/20260117-043512-thread_main-user_123456.png
/project/tmp/input-files/celestial/20260117-043512-thread_1328-user_123456.pdf
```

**Filename format:**
```
{YYYYMMDD-HHMMSS}-thread_{thread_id}-user_{user_id}.{ext}
```

Multiple files in one message:
```
20260117-043512-thread_1328-user_123456.png
20260117-043512-thread_1328-user_123456-2.png
20260117-043512-thread_1328-user_123456-3.png
```

For main thread (no topic): `thread_main`

### Message Format to Claude

With caption:
```
User's caption text here

📎 ./tmp/input-files/celestial/20260117-043512-thread_1328-user_123456.png
```

Without caption:
```
📎 ./tmp/input-files/celestial/20260117-043512-thread_1328-user_123456.png
```

Multiple files:
```
Check these mockups

📎 ./tmp/input-files/celestial/20260117-043512-thread_1328-user_123456.png
📎 ./tmp/input-files/celestial/20260117-043512-thread_1328-user_123456-2.png
```

## Security

### Threats and Mitigations

| Threat | Risk | Mitigation |
|--------|------|------------|
| Path traversal | HIGH | Generated filenames only (no user input in path) |
| Filename injection | HIGH | IDs only, no user-provided names |
| Disk exhaustion | LOW | Telegram limits (20MB photos, 50MB files) + size check |
| Malicious content | LOW | Claude already has file access; not a new attack surface |

### Allowed File Types

**Whitelist extensions:**
- Images: `png`, `jpg`, `jpeg`, `gif`, `webp`
- Documents: `pdf`, `txt`, `md`, `json`, `csv`, `xml`, `yaml`, `yml`

**Blocked:**
- Video: `mp4`, `mov`, `avi`, `mkv`, `webm` (future: Whisper)
- Audio: `mp3`, `ogg`, `wav`, `m4a`, `opus` (future: Whisper)

**Size limit:** 20MB (matches Telegram photo limit)

### Path Validation

Before writing:
1. Generate filename from template (no user input)
2. Construct full path
3. Resolve with `Path.resolve()`
4. Verify with `resolved.is_relative_to(base.resolve())` — NOT string startswith!
5. Create parent directories if needed
6. Download file via callback

```python
# Correct path traversal check (Python 3.9+)
if not resolved.is_relative_to(base_resolved):
    raise ValueError(f"Path {resolved} is outside allowed directory")
```

## Implementation

### New Files

- `src/codogram/services/file_input.py` — FileInputService with callback pattern

### Modified Files

- `src/codogram/handlers/messages.py` — handle photo/document messages

### Domain Types

```python
@dataclass
class FileInfo:
    file_id: str
    extension: str
    size: int

@dataclass
class FileInputResult:
    success: bool = False
    path: Path | None = None
    error: str | None = None  # "unsupported_type", "too_large", "download_failed"

# Callback type - handler provides this, service calls it
DownloadFn = Callable[[str, str], Awaitable[None]]  # (file_id, destination) -> None
```

### FileInputService

```python
class FileInputService:
    ALLOWED_EXTENSIONS = {
        'png', 'jpg', 'jpeg', 'gif', 'webp',  # images
        'pdf', 'txt', 'md', 'json', 'csv', 'xml', 'yaml', 'yml'  # docs
    }
    MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20MB

    def extract_info(self, message) -> FileInfo | None:
        """Extract file info from message. Returns None for video/audio/blocked types."""
        ...

    async def save_file(
        self,
        file_info: FileInfo,
        cwd: str,
        thread_name: str,
        thread_id: int | None,
        user_id: int,
        download_fn: DownloadFn  # Callback - service doesn't know about aiogram
    ) -> FileInputResult:
        """Validate, build path, download via callback, return result."""
        ...

    def format_message(self, caption: str | None, paths: list[Path], cwd: str) -> str:
        """Format message with caption and file paths for tmux."""
        ...
```

### Handler Integration

```python
async def _handle_file_message(message, result, telegram_queue):
    # 1. Extract info
    file_info = _file_input.extract_info(message)
    if not file_info:
        await telegram_queue.reply(message, "Video/audio not supported yet")
        return

    # 2. Create download callback (closure over bot)
    async def download(file_id: str, destination: str):
        await message.bot.download(file_id, destination=destination)

    # 3. Call service with callback
    save_result = await _file_input.save_file(
        file_info=file_info,
        cwd=result.cwd,
        thread_name=result.thread.name,
        thread_id=message.message_thread_id,
        user_id=message.from_user.id,
        download_fn=download
    )

    # 4. Handle result
    if not save_result.success:
        await telegram_queue.reply(message, ERROR_MESSAGES[save_result.error])
        return

    # 5. Format and send to tmux
    content = _file_input.format_message(message.caption, [save_result.path], result.cwd)
    _message_router.send_to_tmux(result, content)
```

## Edge Cases

1. **No project registered** — ignore file (same as text messages)
2. **Thread not found** — create pending thread, ignore file
3. **File too large** — reply with error message
4. **Unsupported type** — reply with "Unsupported file type. Supported: ..."
5. **Download failed** — reply with error, log details
6. **Disk write failed** — reply with error, log details

## Testing

### E2E Tests

1. Send photo → Claude describes it
2. Send photo with caption → caption + path sent to Claude
3. Send document (PDF) → Claude reads it
4. Send multiple photos → all paths sent
5. Send video → rejected with message
6. Send audio → rejected with message
7. Send oversized file → rejected with message

## Future Work

- Audio/video via Whisper transcription
- Cleanup old files (>7 days)
- File type detection via magic bytes
