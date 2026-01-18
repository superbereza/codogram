"""DM onboarding services."""
from .validation import (
    ValidationResult,
    check_base_dir_configured,
    check_base_dir_exists,
    check_binary_available,
    run_critical_checks,
    run_warning_checks,
)
from .onboarding import (
    get_slide_content,
    get_total_slides,
    format_validation_errors,
    format_validation_warnings,
)

__all__ = [
    "ValidationResult",
    "check_base_dir_configured",
    "check_base_dir_exists",
    "check_binary_available",
    "run_critical_checks",
    "run_warning_checks",
    "get_slide_content",
    "get_total_slides",
    "format_validation_errors",
    "format_validation_warnings",
]
