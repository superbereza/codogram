"""Domain types for create flow (branch/thread)."""
from enum import Enum


class CreateType(Enum):
    """Type of entity to create."""
    BRANCH = "branch"
    THREAD = "thread"
