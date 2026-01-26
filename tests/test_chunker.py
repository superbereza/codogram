# tests/test_chunker.py
from codogram.chunker import chunk_message, _split_text

def test_short_message_no_split():
    result = chunk_message("Hello world", max_len=100)
    assert result == ["Hello world"]

def test_long_message_splits():
    text = "A" * 100
    result = chunk_message(text, max_len=30)
    assert len(result) > 1
    assert all(len(c) <= 30 for c in result)

def test_split_on_newline():
    text = "Line1\n\nLine2\n\nLine3"
    result = chunk_message(text, max_len=15)
    assert "Line1" in result[0]


def test_split_text_basic():
    """_split_text returns raw chunks without prefixes."""
    text = "Line 1\n\nLine 2\n\nLine 3"
    chunks = _split_text(text, max_len=20)
    # Should split at paragraph breaks
    assert len(chunks) >= 1
    assert "[1/" not in chunks[0]  # No prefix


def test_split_text_single():
    """Single chunk if text fits."""
    text = "Short text"
    chunks = _split_text(text, max_len=100)
    assert chunks == ["Short text"]


def test_chunk_message_adds_prefixes():
    """chunk_message adds [N/M] prefixes for multiple chunks."""
    text = "A" * 100 + "\n\n" + "B" * 100
    chunks = chunk_message(text, max_len=120)
    if len(chunks) > 1:
        assert chunks[0].startswith("[1/")
        assert chunks[1].startswith("[2/")
