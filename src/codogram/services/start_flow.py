"""Backward compatibility - import from services.start instead."""
from .start import (
    FlowAction, FlowResult, StartFlowService,
    build_announcement, build_thread_announcement, is_setup_phase,
)
from .reset.service import CleanupResult, ResetService

# Re-export cleanup_project as function for backward compat
def cleanup_project(project, delete_directory: bool) -> CleanupResult:
    """Backward compat wrapper for ResetService.cleanup."""
    from ..core.session_manager import project_manager
    service = ResetService(project_manager)
    return service.cleanup(project, delete_directory)

__all__ = [
    "FlowAction", "FlowResult", "StartFlowService", "CleanupResult",
    "build_announcement", "build_thread_announcement",
    "is_setup_phase", "cleanup_project",
]
