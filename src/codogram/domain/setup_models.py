# src/codogram/domain/setup_models.py
"""Data models for setup flow."""
from dataclasses import dataclass, asdict
from typing import Literal


SetupType = Literal["clone", "connect", "new"]


@dataclass
class SetupContext:
    """Typed context for setup flow FSM data.

    Prevents typos in key names and provides autocomplete.
    """
    setup_type: SetupType | None = None
    project_name: str | None = None
    clone_url: str | None = None
    target_dir: str | None = None
    rename_to: str | None = None
    git_choice: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SetupContext":
        """Create from FSM data dict."""
        return cls(
            setup_type=data.get("setup_type"),
            project_name=data.get("project_name"),
            clone_url=data.get("clone_url"),
            target_dir=data.get("target_dir"),
            rename_to=data.get("rename_to"),
            git_choice=data.get("git_choice"),
        )

    def to_dict(self) -> dict:
        """Convert to dict for FSM storage."""
        return {k: v for k, v in asdict(self).items() if v is not None}
