"""Domain models for conversation data."""
from dataclasses import dataclass


@dataclass
class StartFlowData:
    """Data stored during /start flow.

    Additional fields (tmux_name, thread_id) will be added in Phase 7
    when FSM migration happens.
    """

    project: str | None = None
    path: str | None = None
