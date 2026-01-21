# src/codogram/claude/poller/processors/__init__.py
"""Poller processors - each handles one concern."""
from .compact import CompactProcessor
from .permissions import PermissionProcessor
from .stuck import StuckProcessor
from .suggestions import SuggestionsProcessor
from .thinking import ThinkingProcessor

__all__ = [
    "CompactProcessor",
    "PermissionProcessor",
    "StuckProcessor",
    "SuggestionsProcessor",
    "ThinkingProcessor",
]
