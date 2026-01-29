# src/codogram/chunker.py
from .config import TELEGRAM_MESSAGE_MAX_LENGTH


def _split_text(text: str, max_len: int) -> list[str]:
    """Split text at natural breakpoints (paragraphs -> lines -> sentences).

    Returns raw chunks without prefixes.
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        # Find best split point
        chunk = remaining[:max_len]
        split_at = max_len

        # Try paragraph break
        para = chunk.rfind("\n\n")
        if para > max_len // 2:
            split_at = para + 2
        else:
            # Try line break
            line = chunk.rfind("\n")
            if line > max_len // 2:
                split_at = line + 1
            else:
                # Try sentence
                for sep in (". ", "! ", "? "):
                    pos = chunk.rfind(sep)
                    if pos > max_len // 2:
                        split_at = pos + len(sep)
                        break

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    return chunks


def chunk_message(text: str, max_len: int = TELEGRAM_MESSAGE_MAX_LENGTH) -> list[str]:
    """Split text into chunks with [N/M] prefixes for multi-message sending."""
    # Reserve space for prefix "[N/M]\n" (max ~10 chars)
    prefix_reserve = 10
    chunks = _split_text(text, max_len - prefix_reserve)

    # Add prefixes if multiple chunks
    if len(chunks) > 1:
        chunks = [f"[{i+1}/{len(chunks)}]\n{c}" for i, c in enumerate(chunks)]

    return chunks
