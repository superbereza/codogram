# src/codogram/services/setup/git_operations.py
"""Git operations service."""
import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GitResult:
    """Result of a git operation."""
    success: bool
    error: str | None = None
    output: str | None = None


async def git_init(target_dir: Path) -> GitResult:
    """Initialize git repository.

    Args:
        target_dir: Directory to initialize

    Returns:
        GitResult with success/error
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "git", "init",
            cwd=str(target_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return GitResult(
                success=False,
                error=stderr.decode().strip() or "git init failed",
            )

        return GitResult(success=True, output=stdout.decode().strip())

    except Exception as e:
        logger.exception(f"git init failed: {e}")
        return GitResult(success=False, error=str(e))


async def check_gh_cli() -> GitResult:
    """Check if gh CLI is installed and authenticated.

    Returns:
        GitResult with success if gh is ready to use
    """
    # Check if installed
    if not shutil.which("gh"):
        return GitResult(
            success=False,
            error="gh CLI not installed. Install from https://cli.github.com",
        )

    # Check if authenticated
    try:
        process = await asyncio.create_subprocess_exec(
            "gh", "auth", "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            return GitResult(
                success=False,
                error="gh CLI not authenticated. Run `gh auth login` first",
            )

        return GitResult(success=True)

    except Exception as e:
        return GitResult(success=False, error=str(e))


async def gh_repo_create(target_dir: Path, name: str, private: bool = True) -> GitResult:
    """Create GitHub repo using gh CLI.

    Args:
        target_dir: Local directory
        name: Repository name
        private: Create private repo (default True)
    """
    check = await check_gh_cli()
    if not check.success:
        return check

    try:
        args = ["gh", "repo", "create", name, "--source", str(target_dir)]
        if private:
            args.append("--private")
        else:
            args.append("--public")

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return GitResult(
                success=False,
                error=stderr.decode().strip() or "gh repo create failed",
            )

        return GitResult(success=True, output=stdout.decode().strip())

    except Exception as e:
        logger.exception(f"gh repo create failed: {e}")
        return GitResult(success=False, error=str(e))
