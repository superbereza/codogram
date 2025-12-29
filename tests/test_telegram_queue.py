# tests/test_telegram_queue.py
import pytest
from codogram.telegram_queue import OutgoingBatch


def test_outgoing_batch_creation():
    batch = OutgoingBatch(
        chat_id=123,
        thread_id=456,
        messages=[{"text": "hello", "parse_mode": "Markdown"}]
    )
    assert batch.chat_id == 123
    assert batch.thread_id == 456
    assert len(batch.messages) == 1


def test_outgoing_batch_without_thread():
    batch = OutgoingBatch(chat_id=123, thread_id=None, messages=[{"text": "hi"}])
    assert batch.thread_id is None
