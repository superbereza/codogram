"""Read session info from Claude's history.jsonl with incremental reading."""
import json
from pathlib import Path

from .logging_config import logger

HISTORY_PATH = Path.home() / ".claude" / "history.jsonl"

# State for incremental reading.
#
# Caching strategy:
# - _last_size: File size at last read. Used to seek and read only new content.
# - _last_mtime: File modification time. Quick check for "no changes" case.
# - _session_cache: Maps cwd -> session_id. Updated incrementally as new entries appear.
#
# Truncation detection:
# When current_size < _last_size, file was truncated/recreated. We reset _last_size to 0
# and clear the cache. On the next check, current_size > _last_size (0) will be true,
# so we read from the beginning and rebuild the cache from scratch.
_last_size = 0
_last_mtime = 0
_session_cache: dict[str, str] = {}  # cwd -> session_id


def find_session_for_project(cwd: str, history_path: Path = HISTORY_PATH) -> str | None:
    """Find the most recent session_id for a project by cwd.

    Uses incremental reading - only reads new lines since last check.
    Detects file truncation and resets cache when needed.
    """
    global _last_size, _last_mtime, _session_cache

    if not history_path.exists():
        return _session_cache.get(cwd)

    try:
        stat = history_path.stat()
        current_size = stat.st_size
        current_mtime = stat.st_mtime

        # Quick mtime check - no changes
        if current_mtime == _last_mtime and current_size == _last_size:
            return _session_cache.get(cwd)

        # File truncated/recreated - reset cache and re-read from start
        if current_size < _last_size:
            _last_size = 0
            _session_cache.clear()

        # Read only new content
        if current_size > _last_size:
            with open(history_path, 'r') as f:
                f.seek(_last_size)
                new_content = f.read()
            _last_size = current_size

            # Parse new lines and update cache
            new_lines = [line for line in new_content.splitlines() if line.strip()]
            for line in new_lines:
                try:
                    entry = json.loads(line)
                    project = entry.get("project")
                    session_id = entry.get("sessionId")
                    if project and session_id:
                        _session_cache[project] = session_id
                except json.JSONDecodeError:
                    logger.warning("json_decode_error", extra={"line": line[:50]})
                    continue  # Skip malformed lines

            logger.debug(
                "history_read",
                extra={
                    "new_lines": len(new_lines),
                    "cache_size": len(_session_cache)
                }
            )

        _last_mtime = current_mtime
        return _session_cache.get(cwd)

    except PermissionError as e:
        logger.error("permission_denied", extra={"error": str(e)})
        return _session_cache.get(cwd)
    except OSError as e:
        logger.warning("os_error", extra={"error": str(e)})
        return _session_cache.get(cwd)
    except Exception as e:
        logger.warning("history_read_error", extra={"error": str(e)})
        return _session_cache.get(cwd)


def reset_history_cache() -> None:
    """Reset cache (for testing)."""
    global _last_size, _last_mtime, _session_cache
    _last_size = 0
    _last_mtime = 0
    _session_cache = {}


def get_last_user_message_from_jsonl(jsonl_path: Path) -> str | None:
    """Read the last user message from a session jsonl file."""
    if not jsonl_path.exists():
        return None

    try:
        last_user_msg = None
        with open(jsonl_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "user":
                        # Extract text from user message
                        content = entry.get("message", {}).get("content")
                        if isinstance(content, str):
                            # External messages (from Telegram) have plain string content
                            last_user_msg = content
                        elif isinstance(content, list):
                            # Internal Claude messages have array of content blocks
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    last_user_msg = item.get("text")
                                    break
                except json.JSONDecodeError:
                    continue
        return last_user_msg
    except Exception:
        return None


def compute_jsonl_path(cwd: str, session_id: str) -> Path:
    """Compute jsonl path from cwd and session_id.

    Formula: ~/.claude/projects/{normalized_cwd.replace("/", "-")}/{session_id}.jsonl

    Normalization:
    - Remove trailing slashes (except for root "/")
    - Collapse double slashes
    - Do NOT resolve symlinks (match Claude behavior)
    """
    # Normalize path
    normalized = cwd.rstrip("/") or "/"  # Preserve "/" for root
    while "//" in normalized:
        normalized = normalized.replace("//", "/")

    project_hash = normalized.replace("/", "-")
    return Path.home() / ".claude" / "projects" / project_hash / f"{session_id}.jsonl"
