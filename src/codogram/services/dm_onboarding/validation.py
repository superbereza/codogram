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
            message="BASE_DIR не указан в .env",
            fix_hint="Добавь BASE_DIR=/path/to/projects в .env"
        )
    return ValidationResult(ok=True, name="BASE_DIR configured", message="")


def check_base_dir_exists() -> ValidationResult:
    """Check that BASE_DIR path exists on disk."""
    if not settings.base_dir:
        return ValidationResult(
            ok=False,
            name="BASE_DIR exists",
            message="BASE_DIR не указан",
            fix_hint=""
        )

    path = Path(settings.base_dir)
    if not path.exists():
        return ValidationResult(
            ok=False,
            name="BASE_DIR exists",
            message=f"Директория {settings.base_dir} не существует",
            fix_hint=f"mkdir -p {settings.base_dir}"
        )
    return ValidationResult(ok=True, name="BASE_DIR exists", message="")


def check_binary_available(binary: str) -> ValidationResult:
    """Check that a binary is available in PATH."""
    if shutil.which(binary) is None:
        return ValidationResult(
            ok=False,
            name=f"{binary} available",
            message=f"`{binary}` не найден в PATH",
            fix_hint=f"Установи {binary} и добавь в PATH"
        )
    return ValidationResult(ok=True, name=f"{binary} available", message="")


def run_critical_checks() -> list[ValidationResult]:
    """Run all critical validation checks."""
    return [
        check_base_dir_configured(),
        check_base_dir_exists(),
        check_binary_available("claude"),
        check_binary_available("tmux"),
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
                message="git user.name или user.email не настроен",
                fix_hint="git config --global user.name 'Your Name'\ngit config --global user.email 'you@example.com'"
            )
    except Exception:
        return ValidationResult(
            ok=False,
            name="git configured",
            message="Не удалось проверить git config",
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
                name="gh auth",
                message="GitHub CLI не авторизован",
                fix_hint="gh auth login"
            )
    except FileNotFoundError:
        return ValidationResult(
            ok=False,
            name="gh auth",
            message="gh CLI не установлен",
            fix_hint="Установи GitHub CLI: https://cli.github.com/"
        )
    except Exception:
        return ValidationResult(
            ok=False,
            name="gh auth",
            message="Не удалось проверить gh auth",
            fix_hint=""
        )
    return ValidationResult(ok=True, name="gh auth", message="")


def check_ssh_keys() -> ValidationResult:
    """Check if SSH keys exist."""
    ssh_dir = Path.home() / ".ssh"
    key_patterns = ["id_rsa", "id_ed25519", "id_ecdsa"]

    for pattern in key_patterns:
        if (ssh_dir / pattern).exists():
            return ValidationResult(ok=True, name="SSH keys", message="")

    return ValidationResult(
        ok=False,
        name="SSH keys",
        message="SSH ключи не найдены",
        fix_hint="ssh-keygen -t ed25519"
    )


def run_warning_checks() -> list[ValidationResult]:
    """Run all warning validation checks."""
    return [
        check_git_configured(),
        check_gh_auth(),
        check_ssh_keys(),
    ]
