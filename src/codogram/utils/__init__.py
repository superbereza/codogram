"""Utility functions."""
from datetime import datetime, timezone

from .truncate import truncate_body
from ..strings import STALE_BUTTON_SECONDS


def is_stale_callback(message_date: datetime) -> bool:
    """Check if callback button is stale (>5 minutes old).

    Per design: ignore callback_query.message.date if older than 5 minutes.
    """
    now = datetime.now(timezone.utc)
    age_seconds = (now - message_date).total_seconds()
    return age_seconds > STALE_BUTTON_SECONDS


__all__ = ["truncate_body", "is_stale_callback"]
