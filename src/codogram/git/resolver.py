from pathlib import Path

def get_project_name(cwd: Path) -> str:
    """
    Get project name for chat mapping.
    Worktree -> main repository name.
    """
    git_path = cwd / ".git"

    # Worktree: .git is a file with gitdir
    if git_path.is_file():
        content = git_path.read_text().strip()
        if content.startswith("gitdir:"):
            gitdir = Path(content.split(":", 1)[1].strip())
            # .git/worktrees/xxx -> .git -> repo folder
            main_repo = gitdir.parent.parent.parent
            return main_repo.name

    # Regular repo or no git - folder name
    return cwd.name
