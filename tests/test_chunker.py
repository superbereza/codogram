# tests/test_chunker.py
from telegram_bridge.chunker import chunk_message

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
