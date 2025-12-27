# src/codogram/errors.py
"""Error handling policy for codogram.

ERROR level (requires attention):
- Bot startup failures
- Telegram API errors (rate limits, auth failures)
- Config parsing failures

WARNING level (expected, recoverable):
- tmux session died
- jsonl file not found
- JSON decode errors in history.jsonl
- Session not found during refresh

INFO level (normal operations):
- Session changed
- Project restored
- Watcher/poller started/stopped

DEBUG level (troubleshooting):
- File read operations
- Cache updates
- mtime checks
"""

class TelegramBridgeError(Exception):
    """Base exception for codogram."""
    pass

class ConfigError(TelegramBridgeError):
    """Configuration error."""
    pass

class SessionDiscoveryError(TelegramBridgeError):
    """Session discovery failed."""
    pass
