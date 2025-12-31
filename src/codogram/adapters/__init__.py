"""Adapters layer - external system wrappers."""
from .telegram import send_with_retry

__all__ = ["send_with_retry"]
