"""Background permission poller - independent of jsonl watcher."""
from enum import Enum


class PollerState(Enum):
    IDLE = "idle"
    DEBOUNCING = "debouncing"
    SHOWING = "showing"
