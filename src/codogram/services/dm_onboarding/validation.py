"""Environment validation for DM onboarding."""
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ...config import settings


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    ok: bool
    name: str
    message: str
    fix_hint: str = ""


def check_base_dir_configured() -> ValidationResult:
    """Check that BASE_DIR is set in config."""
    if not settings.base_dir or settings.base_dir.strip() == "":
        return ValidationResult(
            ok=False,
            name="BASE_DIR configured",
            message="BASE_DIR not set in .env",
            fix_hint="Add BASE_DIR=/path/to/projects to .env"
        )
    return ValidationResult(ok=True, name="BASE_DIR configured", message="")


def check_base_dir_exists() -> ValidationResult:
    """Check that BASE_DIR path exists on disk."""
    if not settings.base_dir:
        return ValidationResult(
            ok=False,
            name="BASE_DIR exists",
            message="BASE_DIR not set",
            fix_hint=""
        )

    path = Path(settings.base_dir)
    if not path.exists():
        return ValidationResult(
            ok=False,
            name="BASE_DIR exists",
            message=f"Directory {settings.base_dir} doesn't exist",
            fix_hint=f"mkdir -p {settings.base_dir}"
        )
    return ValidationResult(ok=True, name="BASE_DIR exists", message="")


def check_binary_available(binary: str) -> ValidationResult:
    """Check that a binary is available in PATH."""
    if shutil.which(binary) is None:
        return ValidationResult(
            ok=False,
            name=f"{binary} available",
            message=f"`{binary}` not found in PATH",
            fix_hint=f"Install {binary} and add to PATH"
        )
    return ValidationResult(ok=True, name=f"{binary} available", message="")


def run_critical_checks() -> list[ValidationResult]:
    """Run all critical validation checks."""
    return [
        check_base_dir_configured(),
        check_base_dir_exists(),
        check_binary_available("tmux"),
        check_binary_available("claude"),
    ]


def check_git_configured() -> ValidationResult:
    """Check if git user.name and user.email are configured."""
    try:
        name = subprocess.run(
            ["git", "config", "--global", "user.name"],
            capture_output=True, text=True, timeout=5
        )
        email = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True, text=True, timeout=5
        )
        if not name.stdout.strip() or not email.stdout.strip():
            return ValidationResult(
                ok=False,
                name="git configured",
                message="git user.name or user.email not set",
                fix_hint="git config --global user.name 'Your Name'"
            )
    except Exception:
        return ValidationResult(
            ok=False,
            name="git configured",
            message="Could not check git config",
            fix_hint=""
        )
    return ValidationResult(ok=True, name="git configured", message="")


def check_gh_auth() -> ValidationResult:
    """Check if GitHub CLI is authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return ValidationResult(
                ok=False,
                name="gh auth configured",
                message="GitHub CLI not authenticated",
                fix_hint="gh auth login"
            )
    except FileNotFoundError:
        return ValidationResult(
            ok=False,
            name="gh auth configured",
            message="gh CLI not installed",
            fix_hint="https://cli.github.com/"
        )
    except Exception:
        return ValidationResult(
            ok=False,
            name="gh auth configured",
            message="Could not check gh auth",
            fix_hint=""
        )
    return ValidationResult(ok=True, name="gh auth configured", message="")


def check_whisper_api_key() -> ValidationResult:
    """Check if OpenAI API key is configured (used for Whisper)."""
    if not settings.openai_api_key or settings.openai_api_key.strip() == "":
        return ValidationResult(
            ok=False,
            name="voice transcription",
            message="OpenAI API key not configured (for voice transcription)",
            fix_hint="Add OPENAI_API_KEY to .env"
        )
    return ValidationResult(ok=True, name="voice transcription", message="")


def run_warning_checks() -> list[ValidationResult]:
    """Run all warning validation checks."""
    return [
        check_git_configured(),
        check_gh_auth(),
        check_whisper_api_key(),
    ]
