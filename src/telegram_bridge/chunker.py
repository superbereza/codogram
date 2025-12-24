# src/telegram_bridge/chunker.py
def chunk_message(text: str, max_len: int = 4000) -> list[str]:
    """Split text into chunks, preferring natural breakpoints."""
    if len(text) <= max_len:
        return [text]

    # Reserve space for chunk prefix "[N/M]\n" (max ~10 chars for reasonable chunk counts)
    prefix_reserve = 10
    effective_max = max_len - prefix_reserve

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= effective_max:
            chunks.append(remaining)
            break

        # Find best split point
        chunk = remaining[:effective_max]
        split_at = effective_max

        # Try paragraph break
        para = chunk.rfind("\n\n")
        if para > effective_max // 2:
            split_at = para + 2
        else:
            # Try line break
            line = chunk.rfind("\n")
            if line > effective_max // 2:
                split_at = line + 1
            else:
                # Try sentence
                for sep in (". ", "! ", "? "):
                    pos = chunk.rfind(sep)
                    if pos > effective_max // 2:
                        split_at = pos + len(sep)
                        break

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    # Add prefixes if multiple chunks
    if len(chunks) > 1:
        chunks = [f"[{i+1}/{len(chunks)}]\n{c}" for i, c in enumerate(chunks)]

    return chunks
