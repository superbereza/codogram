# Git Worktree Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `/branch_create` and `/branch_finish` commands for isolated worktree-based development.

**Architecture:** Each topic (except General) gets its own git worktree with dedicated branch. ThreadInfo stores worktree_path and base_branch. Commands handle worktree lifecycle with proper cleanup.

**Tech Stack:** Python, aiogram, git CLI, tmux

**Design:** See `docs/designs/2025-12-30-git-worktree-support.md`

---

## Task 1: Add worktree fields to ThreadInfo

**Files:**
- Modify: `src/codogram/session_manager.py:82-109`
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
# tests/test_session_manager.py
def test_thread_info_has_worktree_fields():
    from codogram.session_manager import ThreadInfo

    thread = ThreadInfo(thread_id=123, name="auth")
    assert thread.worktree_path is None
    assert thread.base_branch is None
    assert thread.archived is False

    thread_with_worktree = ThreadInfo(
        thread_id=456,
        name="feature",
        worktree_path="/dev/project-feature",
        base_branch="main",
        archived=True
    )
    assert thread_with_worktree.worktree_path == "/dev/project-feature"
    assert thread_with_worktree.base_branch == "main"
    assert thread_with_worktree.archived is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_thread_info_has_worktree_fields -v`
Expected: FAIL with "unexpected keyword argument 'worktree_path'"

**Step 3: Write minimal implementation**

Add to ThreadInfo dataclass after `start_requested_at`:

```python
    # Worktree support:
    worktree_path: str | None = None   # None = main repo directory
    base_branch: str | None = None     # Branch this worktree was created from
    archived: bool = False             # True = topic closed after /branch_finish
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py::test_thread_info_has_worktree_fields -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat(session): add worktree_path and base_branch to ThreadInfo"
```

---

## Task 2: Update config persistence for worktree fields

**Files:**
- Modify: `src/codogram/session_manager.py` (ProjectManager._load_projects, _save_project)
- Test: `tests/test_session_manager.py`

**Step 1: Write the failing test**

```python
def test_worktree_fields_persist_to_config(tmp_path, monkeypatch):
    import json
    from codogram.session_manager import ProjectManager, ThreadInfo

    config_file = tmp_path / ".config.json"
    config_file.write_text("{}")

    monkeypatch.setattr("codogram.session_manager.load_config", lambda: {})
    monkeypatch.setattr("codogram.session_manager.save_config", lambda c: config_file.write_text(json.dumps(c)))

    pm = ProjectManager()
    project = pm.get_or_create_project("test-project")
    project.chat_id = 123
    project.cwd = "/dev/test-project"

    thread = project.get_or_create_thread(456, "auth")
    thread.worktree_path = "/dev/test-project-auth"
    thread.base_branch = "main"
    thread.archived = True

    pm.save_project(project)

    saved = json.loads(config_file.read_text())
    thread_data = saved["projects"]["test-project"]["threads"]["456"]
    assert thread_data["worktree_path"] == "/dev/test-project-auth"
    assert thread_data["base_branch"] == "main"
    assert thread_data["archived"] is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_worktree_fields_persist_to_config -v`
Expected: FAIL (worktree_path not in saved data)

**Step 3: Update _save_project method**

Find where thread data is serialized and add:

```python
if thread.worktree_path:
    thread_data["worktree_path"] = thread.worktree_path
if thread.base_branch:
    thread_data["base_branch"] = thread.base_branch
if thread.archived:
    thread_data["archived"] = thread.archived
```

**Step 4: Update _load_projects method**

Where ThreadInfo is created from saved data, add:

```python
worktree_path=thread_data.get("worktree_path"),
base_branch=thread_data.get("base_branch"),
archived=thread_data.get("archived", False),
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py::test_worktree_fields_persist_to_config -v`
Expected: PASS

**Step 6: Write test for loading worktree fields**

```python
def test_worktree_fields_load_from_config(tmp_path, monkeypatch):
    import json
    from codogram.session_manager import ProjectManager

    config_data = {
        "projects": {
            "test-project": {
                "chat_id": 123,
                "cwd": "/dev/test-project",
                "threads": {
                    "456": {
                        "name": "auth",
                        "worktree_path": "/dev/test-project-auth",
                        "base_branch": "main",
                        "archived": True
                    }
                }
            }
        }
    }

    monkeypatch.setattr("codogram.session_manager.load_config", lambda: config_data)
    monkeypatch.setattr("codogram.session_manager.save_config", lambda c: None)

    pm = ProjectManager()
    project = pm.get("test-project")
    thread = project.get_thread(456)

    assert thread.worktree_path == "/dev/test-project-auth"
    assert thread.base_branch == "main"
    assert thread.archived is True
```

**Step 7: Run test to verify it passes**

Run: `pytest tests/test_session_manager.py::test_worktree_fields_load_from_config -v`
Expected: PASS

**Step 8: Commit**

```bash
git add src/codogram/session_manager.py tests/test_session_manager.py
git commit -m "feat(config): persist worktree_path and base_branch"
```

---

## Task 3: Create git utility module

**Files:**
- Create: `src/codogram/git_utils.py`
- Test: `tests/test_git_utils.py`

**Step 1: Write tests for all utilities**

```python
# tests/test_git_utils.py
import subprocess
from pathlib import Path


def test_sanitize_branch_name():
    from codogram.git_utils import sanitize_branch_name

    assert sanitize_branch_name("feature/auth") == "feature-auth"
    assert sanitize_branch_name("fix login bug") == "fix-login-bug"
    assert sanitize_branch_name("feature@#$auth") == "featureauth"
    assert sanitize_branch_name("UPPER-case") == "upper-case"


def test_get_default_branch(tmp_path, monkeypatch):
    from codogram.git_utils import get_default_branch

    # Create a git repo with main branch
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
    (tmp_path / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    assert get_default_branch(tmp_path) == "main"


def test_branch_exists(tmp_path):
    from codogram.git_utils import branch_exists

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
    (tmp_path / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    assert branch_exists(tmp_path, "main") is True
    assert branch_exists(tmp_path, "nonexistent") is False


def test_has_uncommitted_changes(tmp_path):
    from codogram.git_utils import has_uncommitted_changes

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp_path, capture_output=True)
    (tmp_path / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    assert has_uncommitted_changes(tmp_path) is False

    (tmp_path / "file.txt").write_text("modified")
    assert has_uncommitted_changes(tmp_path) is True


def test_is_git_repo(tmp_path):
    from codogram.git_utils import is_git_repo

    assert is_git_repo(tmp_path) is False

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    assert is_git_repo(tmp_path) is True


def test_max_branch_name_length():
    from codogram.git_utils import max_branch_name_length

    assert max_branch_name_length("codogram") == 37  # 45 - 8
    assert max_branch_name_length("my-long-project") == 30  # 45 - 15
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git_utils.py -v`
Expected: FAIL with "No module named 'codogram.git_utils'"

**Step 3: Write implementation**

```python
# src/codogram/git_utils.py
"""Git utility functions for worktree support."""
import re
import subprocess
from pathlib import Path


def sanitize_branch_name(name: str) -> str:
    """Sanitize branch name: lowercase, replace invalid chars."""
    name = name.lower()
    name = re.sub(r'[/\s]+', '-', name)  # slashes and spaces to dashes
    name = re.sub(r'[^a-z0-9_-]', '', name)  # remove invalid chars
    return name


def get_default_branch(repo_path: Path) -> str:
    """Get default branch name (main, master, etc.)."""
    # Try remote HEAD first
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        # refs/remotes/origin/main -> main
        return result.stdout.strip().split('/')[-1]

    # Try local config
    result = subprocess.run(
        ["git", "config", "--get", "init.defaultBranch"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # Check if main exists
    if branch_exists(repo_path, "main"):
        return "main"

    # Check if master exists
    if branch_exists(repo_path, "master"):
        return "master"

    # Fallback to current branch
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    return "main"  # ultimate fallback


def branch_exists(repo_path: Path, branch_name: str) -> bool:
    """Check if branch exists in repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        cwd=repo_path,
        capture_output=True
    )
    return result.returncode == 0


def has_uncommitted_changes(repo_path: Path) -> bool:
    """Check if repo has uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


def is_git_repo(path: Path) -> bool:
    """Check if path is a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=path,
        capture_output=True
    )
    return result.returncode == 0


def max_branch_name_length(project_name: str) -> int:
    """Calculate max branch name length for project."""
    return 45 - len(project_name)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_git_utils.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/git_utils.py tests/test_git_utils.py
git commit -m "feat(git): add git utility functions for worktree support"
```

---

## Task 4: Create worktree operations module

**Files:**
- Create: `src/codogram/worktree.py`
- Test: `tests/test_worktree.py`

**Step 1: Write tests**

```python
# tests/test_worktree.py
import subprocess
from pathlib import Path


def test_create_worktree(tmp_path):
    from codogram.worktree import create_worktree

    # Setup main repo
    main_repo = tmp_path / "project"
    main_repo.mkdir()
    subprocess.run(["git", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=main_repo, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, capture_output=True)

    worktree_path = tmp_path / "project-feature"

    result = create_worktree(
        main_repo=main_repo,
        worktree_path=worktree_path,
        branch_name="feature",
        base_branch="main"
    )

    assert result.success is True
    assert worktree_path.exists()
    assert (worktree_path / "file.txt").exists()


def test_create_worktree_branch_exists(tmp_path):
    from codogram.worktree import create_worktree

    main_repo = tmp_path / "project"
    main_repo.mkdir()
    subprocess.run(["git", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=main_repo, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=main_repo, capture_output=True)

    worktree_path = tmp_path / "project-feature"

    result = create_worktree(
        main_repo=main_repo,
        worktree_path=worktree_path,
        branch_name="feature",
        base_branch="main"
    )

    assert result.success is False
    assert "already exists" in result.error


def test_remove_worktree(tmp_path):
    from codogram.worktree import create_worktree, remove_worktree

    main_repo = tmp_path / "project"
    main_repo.mkdir()
    subprocess.run(["git", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=main_repo, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, capture_output=True)

    worktree_path = tmp_path / "project-feature"
    create_worktree(main_repo, worktree_path, "feature", "main")

    result = remove_worktree(main_repo, worktree_path, "feature", delete_branch=True)

    assert result.success is True
    assert not worktree_path.exists()


def test_merge_branch(tmp_path):
    from codogram.worktree import create_worktree, merge_branch

    main_repo = tmp_path / "project"
    main_repo.mkdir()
    subprocess.run(["git", "init"], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=main_repo, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, capture_output=True)

    worktree_path = tmp_path / "project-feature"
    create_worktree(main_repo, worktree_path, "feature", "main")

    # Make changes in worktree
    (worktree_path / "new_file.txt").write_text("new")
    subprocess.run(["git", "add", "."], cwd=worktree_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add new file"], cwd=worktree_path, capture_output=True)

    result = merge_branch(main_repo, "feature", "main")

    assert result.success is True
    assert (main_repo / "new_file.txt").exists()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktree.py -v`
Expected: FAIL with "No module named 'codogram.worktree'"

**Step 3: Write implementation**

```python
# src/codogram/worktree.py
"""Git worktree operations."""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .git_utils import branch_exists


@dataclass
class WorktreeResult:
    success: bool
    error: str | None = None


def create_worktree(
    main_repo: Path,
    worktree_path: Path,
    branch_name: str,
    base_branch: str
) -> WorktreeResult:
    """Create a new worktree with a new branch."""
    if worktree_path.exists():
        return WorktreeResult(False, f"Directory {worktree_path} already exists")

    if branch_exists(main_repo, branch_name):
        return WorktreeResult(False, f"Branch '{branch_name}' already exists")

    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_path), base_branch],
        cwd=main_repo,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return WorktreeResult(False, result.stderr.strip())

    return WorktreeResult(True)


def remove_worktree(
    main_repo: Path,
    worktree_path: Path,
    branch_name: str,
    delete_branch: bool = True,
    force: bool = False
) -> WorktreeResult:
    """Remove worktree and optionally delete branch."""

    # Remove worktree
    if worktree_path.exists():
        cmd = ["git", "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))

        result = subprocess.run(cmd, cwd=main_repo, capture_output=True, text=True)
        if result.returncode != 0:
            return WorktreeResult(False, result.stderr.strip())

    # Delete branch
    if delete_branch and branch_name and branch_exists(main_repo, branch_name):
        flag = "-D" if force else "-d"
        result = subprocess.run(
            ["git", "branch", flag, branch_name],
            cwd=main_repo,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return WorktreeResult(False, result.stderr.strip())

    return WorktreeResult(True)


def merge_branch(
    main_repo: Path,
    source_branch: str,
    target_branch: str
) -> WorktreeResult:
    """Merge source branch into target branch."""
    # Checkout target
    result = subprocess.run(
        ["git", "checkout", target_branch],
        cwd=main_repo,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return WorktreeResult(False, f"Failed to checkout {target_branch}: {result.stderr}")

    # Merge
    result = subprocess.run(
        ["git", "merge", source_branch],
        cwd=main_repo,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
            return WorktreeResult(False, "Merge conflicts detected")
        return WorktreeResult(False, result.stderr.strip())

    return WorktreeResult(True)


def push_branch(main_repo: Path, branch_name: str) -> WorktreeResult:
    """Push branch to origin."""
    # Check if remote exists
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=main_repo,
        capture_output=True
    )
    if result.returncode != 0:
        return WorktreeResult(True)  # No remote, skip silently

    result = subprocess.run(
        ["git", "push", "origin", branch_name],
        cwd=main_repo,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return WorktreeResult(False, result.stderr.strip())

    return WorktreeResult(True)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktree.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/worktree.py tests/test_worktree.py
git commit -m "feat(worktree): add worktree operations module"
```

---

## Task 5: Update magic_names for suffix fallback

**Files:**
- Modify: `src/codogram/magic_names.py`
- Test: `tests/test_magic_names.py`

**Step 1: Write the failing test**

```python
def test_magic_names_suffix_fallback():
    from codogram.magic_names import get_random_magic_name, MAGIC_NAMES

    # All base names taken
    excluded = set(MAGIC_NAMES)
    name = get_random_magic_name(excluded)

    # Should return name with suffix
    assert "-" in name
    base, suffix = name.rsplit("-", 1)
    assert base in MAGIC_NAMES
    assert suffix.isdigit()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_magic_names.py::test_magic_names_suffix_fallback -v`
Expected: FAIL (currently raises or returns None)

**Step 3: Update implementation**

```python
# In get_random_magic_name, after checking available is empty:
if not available:
    # Try with suffixes
    for suffix in range(2, 100):
        for base_name in MAGIC_NAMES:
            candidate = f"{base_name}-{suffix}"
            if candidate not in excluded:
                return candidate
    raise ValueError("All magic names exhausted")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_magic_names.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/magic_names.py tests/test_magic_names.py
git commit -m "feat(magic_names): add suffix fallback when all names taken"
```

---

## Task 6: Create services/launch.py with shared thread creation logic

**Files:**
- Create: `src/codogram/services/__init__.py`
- Create: `src/codogram/services/launch.py`
- Modify: `src/codogram/bot.py` (use new service)

**Step 1: Create services directory**

```bash
mkdir -p src/codogram/services
touch src/codogram/services/__init__.py
```

**Step 2: Create launch.py with shared logic**

```python
# src/codogram/services/launch.py
"""Launch service for creating threads with Claude sessions."""
from pathlib import Path

from aiogram import Bot
from aiogram.types import Message

from ..session_manager import ProjectState, ThreadInfo, project_manager
from ..launch_animation import launch_with_animation


async def create_thread_with_session(
    bot: Bot,
    chat_id: int,
    project: ProjectState,
    name: str,
    worktree_path: str | None = None,
    base_branch: str | None = None,
) -> ThreadInfo | None:
    """
    Create Telegram topic + ThreadInfo + launch Claude.

    Used by both /thread_create and /branch_create.
    """
    # Create Telegram topic
    try:
        topic = await bot.create_forum_topic(chat_id, name.capitalize())
    except Exception as e:
        return None

    thread_id = topic.message_thread_id

    # Create ThreadInfo
    thread = ThreadInfo(thread_id=thread_id, name=name)
    thread.worktree_path = worktree_path
    thread.base_branch = base_branch
    project.threads[thread_id] = thread
    project_manager._save()

    # Determine cwd for Claude
    cwd = worktree_path if worktree_path else project.cwd

    # Launch Claude with animation
    from .._make_task_starters import make_task_starters  # TODO: move to services
    start_poller, start_watcher = make_task_starters(bot)

    tmux_name = thread.get_tmux_session(project.project_name)

    await launch_with_animation(
        bot=bot,
        chat_id=chat_id,
        thread_id=thread_id,
        project=project,
        thread=thread,
        tmux_name=tmux_name,
        cwd=Path(cwd),
        start_poller=start_poller,
        start_watcher=start_watcher,
    )

    return thread
```

**Step 3: Update thread_create to use service**

Refactor `cmd_thread_create` in bot.py to call `create_thread_with_session`.

**Step 4: Commit**

```bash
git add src/codogram/services/
git commit -m "refactor: extract create_thread_with_session to services/launch.py"
```

---

## Task 7: Add /branch_create command

**Files:**
- Modify: `src/codogram/bot.py`
- Test: Manual testing (complex async/telegram interaction)

**Step 1: Add command handler skeleton**

```python
@dp.message(Command("branch_create"))
@admin_only
async def cmd_branch_create(message: types.Message):
    """Create a new worktree branch with isolated Claude session."""
    # Check forum group
    if not message.chat.is_forum:
        await message.answer("`[!]` Topics required for /branch_create. Enable in group settings → Topics")
        return

    project = pm.get_project_by_chat(message.chat.id)
    if not project:
        await message.answer("`[!]` Project not registered. Use /start first.")
        return

    # Check git repo
    from .git_utils import is_git_repo
    if not is_git_repo(Path(project.cwd)):
        await message.answer("`[x]` Git repository required for /branch_create")
        return

    # Parse name argument
    args = message.text.split(maxsplit=1)
    branch_name = args[1] if len(args) > 1 else None

    # TODO: Implement full flow with popups
    await message.answer("`[~]` /branch_create implementation in progress...")
```

**Step 2: Implement uncommitted changes check and popup**

Add inline keyboard for uncommitted changes scenario.

**Step 3: Implement worktree creation**

Use worktree.create_worktree() and create topic/tmux.

**Step 4: Test manually**

Test in Telegram with various scenarios.

**Step 5: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): add /branch_create command"
```

---

## Task 8: Add /branch_finish command

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Add command handler skeleton**

```python
@dp.message(Command("branch_finish"))
@admin_only
async def cmd_branch_finish(message: types.Message):
    """Finish branch: merge and cleanup worktree."""
    thread_id = message.message_thread_id
    project = pm.get_project_by_chat(message.chat.id)

    if not project:
        await message.answer("`[!]` Project not registered.")
        return

    thread = project.get_thread(thread_id)
    if not thread or not thread.worktree_path:
        await message.answer("`[!]` /branch_finish only works in worktree topics. Use /thread_close for this topic.")
        return

    # TODO: Implement merge popup and cleanup
    await message.answer("`[~]` /branch_finish implementation in progress...")
```

**Step 2: Implement merge target popup**

Show buttons: [Merge → main], [Merge → base_branch], [!! Delete without merge], [<< Go back]

**Step 3: Check main directory before merge**

After user selects target branch, check main directory for uncommitted changes:

```python
from .git_utils import has_uncommitted_changes

if has_uncommitted_changes(Path(project.cwd)):
    await callback.message.edit_text(
        "`[!]` Uncommitted changes in main directory. Commit or stash first."
    )
    return
```

**Step 4: Implement merge and cleanup flow**

Use worktree.merge_branch(), push_branch(), remove_worktree().

Cleanup order:
1. Kill tmux session
2. Remove worktree
3. Delete branch
4. Archive topic:
```python
# Close topic and set folder icon
await bot.close_forum_topic(chat_id, thread_id)
await bot.edit_forum_topic(chat_id, thread_id, icon_custom_emoji_id="5357315181649076022")  # 📁
```

**Step 5: Cancel background tasks**

```python
if thread.watcher_task:
    thread.watcher_task.cancel()
if thread.poller_task:
    thread.poller_task.cancel()
if thread.binding_task:
    thread.binding_task.cancel()
```

**Step 6: Update thread state after cleanup**

```python
# Mark as archived (preserves name, base_branch for history)
thread.archived = True
thread.worktree_path = None  # directory deleted
thread.session_id = None
project_manager._save()
```

**Step 7: Test manually**

**Step 8: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): add /branch_finish command"
```

---

## Task 9: Add /thread_create warning + require_forum_group helper

**Files:**
- Create: `src/codogram/handlers/threads.py` (or add to existing handlers file)
- Modify: `src/codogram/bot.py` (cmd_thread_create, cmd_branch_create, cmd_branch_finish)

**Step 1: Create require_forum_group helper**

```python
# src/codogram/handlers/threads.py (or similar)
from aiogram.types import Message


async def require_forum_group(message: Message) -> bool:
    """Check if message is from a forum group. Returns False and sends error if not."""
    if message.chat.type == "private":
        await message.answer("`[!]` This command requires a group with topics.")
        return False
    if not message.chat.is_forum:
        await message.answer("`[!]` Topics required. Enable in group settings → Topics")
        return False
    return True
```

**Step 2: Update /branch_create and /branch_finish to use helper**

Replace inline forum checks with:
```python
if not await require_forum_group(message):
    return
```

**Step 3: Find thread_create handler**

Locate the existing thread creation logic.

**Step 4: Add check for non-worktree threads**

```python
# Before creating new thread in main
non_worktree_threads = [
    t for t in project.threads.values()
    if t.thread_id is not None and t.worktree_path is None
]

if non_worktree_threads:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Create in main anyway", callback_data="thread_create_confirm")],
        [InlineKeyboardButton(text="/branch_create", callback_data="branch_create_redirect")],
        [InlineKeyboardButton(text="[x] Cancel", callback_data="cancel")]
    ])
    await message.answer(
        "`[!]` Topic without isolation exists. Use /branch_create for isolated work.",
        reply_markup=keyboard
    )
    return
```

**Step 5: Add callback handlers**

Handle the button responses.

**Step 6: Test manually**

**Step 7: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): add warning when creating thread without worktree"
```

---

## Task 10: Add project name length check at /start

**Files:**
- Modify: `src/codogram/bot.py` (start command)

**Step 1: Find where project_name is determined**

**Step 2: Add length validation**

```python
if len(project_name) > 35:
    await message.answer(
        "`[!]` Project name too long (max 35 chars). "
        "Rename group or use /register_dir with shorter name."
    )
    return
```

**Step 3: Test manually**

**Step 4: Commit**

```bash
git add src/codogram/bot.py
git commit -m "feat(bot): validate project name length at /start"
```

---

## Task 11: Integration testing

**Files:**
- Test: Manual end-to-end testing

**Step 1: Test /branch_create from General**

1. No uncommitted changes → creates worktree
2. With uncommitted changes → shows popup
3. [Commit first] → sends message to Claude
4. Invalid name → shows error

**Step 2: Test /branch_create from worktree topic**

1. Shows base branch selection popup
2. Creates nested worktree correctly

**Step 3: Test /branch_finish**

1. Merge to main → success
2. Merge conflicts → shows warning
3. Delete without merge → confirms and deletes

**Step 4: Test edge cases**

1. Branch already exists
2. Directory already exists
3. Push fails
4. Worktree deleted manually

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix(worktree): integration testing fixes"
```

---

## Summary

| Task | Description | Est. Complexity |
|------|-------------|-----------------|
| 1 | Add worktree fields to ThreadInfo (incl. archived) | Simple |
| 2 | Update config persistence | Simple |
| 3 | Create git utility module | Medium |
| 4 | Create worktree operations module | Medium |
| 5 | Update magic_names for suffix fallback | Simple |
| 6 | Create services/launch.py with shared logic | Medium |
| 7 | Add /branch_create command | Complex |
| 8 | Add /branch_finish command | Complex |
| 9 | Add /thread_create warning + require_forum_group | Simple |
| 10 | Add project name length check | Simple |
| 11 | Integration testing | Medium |

Total: 11 tasks
