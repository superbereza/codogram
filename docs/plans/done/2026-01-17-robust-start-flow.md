# Robust /start Flow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement atomic /start flow with error recovery, URL validation, /reset_all command, and project-ready checks.

**Architecture:** Two-phase atomicity (filesystem ops before config), FSM retry pattern for URL validation, two-level require helpers (tmux_exists vs claude_ready), multi-step /reset_all with go-back navigation.

**Tech Stack:** Python 3.10+, aiogram 3.4+, unidecode (already in deps), fcntl for file locking

---

## Task 1: Add URL Validation Strings

**Files:**
- Modify: `src/codogram/strings.py:100-130` (add after "Claude status" section)

**Step 1: Write the test**

```python
# tests/test_strings.py
def test_url_validation_strings_exist():
    from codogram import strings

    assert hasattr(strings, 'GIT_URL_INVALID_WIKI')
    assert hasattr(strings, 'GIT_URL_INVALID_BLOB')
    assert hasattr(strings, 'GIT_URL_INVALID_GIST')
    assert hasattr(strings, 'GIT_URL_INVALID_FORMAT')
    assert hasattr(strings, 'GIT_URL_RETRY_PROMPT')
    assert "[x]" in strings.GIT_URL_INVALID_WIKI  # Uses STATUS_ERR
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_strings.py::test_url_validation_strings_exist -v`
Expected: FAIL with `AttributeError`

**Step 3: Add strings**

Add to `src/codogram/strings.py` after line ~112 (after `CLAUDE_NO_RESTART`):

```python
# --- URL Validation ---

GIT_URL_INVALID_WIKI = f"{STATUS_ERR} This is a wiki page, not a repository"
GIT_URL_INVALID_BLOB = f"{STATUS_ERR} This is a file link. Use repository URL"
GIT_URL_INVALID_GIST = f"{STATUS_ERR} Gists cannot be cloned as projects"
GIT_URL_INVALID_FORMAT = f"{STATUS_ERR} Invalid URL. Use https:// or git@ format"
GIT_URL_RETRY_PROMPT = "Send valid repository URL:"
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_strings.py::test_url_validation_strings_exist -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/strings.py tests/test_strings.py && git commit -m "$(cat <<'EOF'
feat(strings): add URL validation error messages

Add GIT_URL_INVALID_WIKI, GIT_URL_INVALID_BLOB, GIT_URL_INVALID_GIST,
GIT_URL_INVALID_FORMAT for git clone URL validation.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Project State and Reset Strings

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Write the test**

```python
# tests/test_strings.py
def test_project_state_strings_exist():
    from codogram import strings

    # Project state
    assert hasattr(strings, 'PROJECT_NOT_READY')
    assert hasattr(strings, 'CLAUDE_STARTING')

    # Clone progress
    assert hasattr(strings, 'CLONE_IN_PROGRESS')

    # Reset flow
    assert hasattr(strings, 'RESET_NO_PROJECT')
    assert hasattr(strings, 'RESET_FLOW_IN_PROGRESS')
    assert hasattr(strings, 'RESET_CLEANUP_FAILED')
    assert hasattr(strings, 'RESET_COMPLETE')
    assert hasattr(strings, 'RESET_CONFIRM')
    assert hasattr(strings, 'RESET_CONFIRM_TOPIC')
    assert hasattr(strings, 'RESET_UNCOMMITTED')
    assert hasattr(strings, 'RESET_DIR_CHOICE')
    assert hasattr(strings, 'RESET_DONE')

    # Buttons
    assert hasattr(strings, 'BTN_CONTINUE')
    assert hasattr(strings, 'BTN_KEEP_DIR')
    assert hasattr(strings, 'BTN_DELETE_DIR')
    assert hasattr(strings, 'BTN_DELETE_ANYWAY')
    assert hasattr(strings, 'BTN_GO_BACK')
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_strings.py::test_project_state_strings_exist -v`
Expected: FAIL with `AttributeError`

**Step 3: Add strings**

Add to `src/codogram/strings.py` after URL validation section:

```python
# --- Project State ---

PROJECT_NOT_READY = f"{STATUS_WARN} Project not ready. Use /start first"
CLAUDE_STARTING = f"{STATUS_WARN} Claude is starting... wait a moment"


# --- Clone Progress ---

CLONE_IN_PROGRESS = f"{STATUS_PENDING} Cloning repository... may take several minutes for large repos"


# --- Reset Flow ---

RESET_FLOW_IN_PROGRESS = f"{STATUS_WARN} Start flow in progress. Wait for completion or use /cancel"
RESET_CLEANUP_FAILED = f"{STATUS_WARN} Could not delete directory `{{path}}`\\n\\nDelete manually: `rm -rf {{path}}`"

RESET_NO_PROJECT = f"{STATUS_INFO} Nothing to reset. Use /start to begin."
RESET_COMPLETE = f"{STATUS_OK} Reset complete. Use /start to begin."
RESET_CONFIRM = f"""{STATUS_QUESTION} Reset project `{{name}}`?

This will disconnect Claude and clear settings."""
RESET_CONFIRM_TOPIC = f"""{STATUS_QUESTION} Reset entire project `{{name}}`?

This will disconnect Claude in all topics and clear settings."""
RESET_UNCOMMITTED = f"{STATUS_WARN} Uncommitted changes in `{{path}}`"
RESET_DIR_CHOICE = f"{STATUS_QUESTION} Delete directory `{{path}}`?"
RESET_DONE = f"""{STATUS_OK} Project reset

• Config cleared
• Claude stopped
• Directory {{dir_status}}

/start to begin new project"""
```

Add to buttons section (around line 165):

```python
BTN_CONTINUE = "Continue"
BTN_KEEP_DIR = "Keep directory"
BTN_DELETE_DIR = "Delete"
BTN_DELETE_ANYWAY = "Delete anyway"
BTN_GO_BACK = "[<<] Go back"
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_strings.py::test_project_state_strings_exist -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/strings.py tests/test_strings.py && git commit -m "$(cat <<'EOF'
feat(strings): add project state and reset flow strings

Add PROJECT_NOT_READY, CLAUDE_STARTING for project state checks.
Add RESET_* strings for /reset_all multi-step flow.
Add BTN_* for reset flow buttons.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Implement validate_git_url()

**Files:**
- Modify: `src/codogram/domain/validators.py`

**Step 1: Write the test**

```python
# tests/test_validators.py
import pytest
from codogram.domain.validators import validate_git_url

class TestValidateGitUrl:
    def test_valid_https_url(self):
        is_valid, error = validate_git_url("https://github.com/user/repo.git")
        assert is_valid is True
        assert error is None

    def test_valid_ssh_url(self):
        is_valid, error = validate_git_url("git@github.com:user/repo.git")
        assert is_valid is True
        assert error is None

    def test_valid_ssh_protocol_url(self):
        is_valid, error = validate_git_url("ssh://git@github.com/user/repo.git")
        assert is_valid is True
        assert error is None

    def test_wiki_url_invalid(self):
        is_valid, error = validate_git_url("https://github.com/user/repo/wiki/Page")
        assert is_valid is False
        assert "wiki" in error.lower()

    def test_blob_url_invalid(self):
        is_valid, error = validate_git_url("https://github.com/user/repo/blob/main/file.py")
        assert is_valid is False
        assert "file" in error.lower()

    def test_tree_url_invalid(self):
        is_valid, error = validate_git_url("https://github.com/user/repo/tree/main/folder")
        assert is_valid is False
        assert "file" in error.lower()

    def test_gist_url_invalid(self):
        is_valid, error = validate_git_url("https://gist.github.com/user/abc123")
        assert is_valid is False
        assert "gist" in error.lower()

    def test_invalid_format(self):
        is_valid, error = validate_git_url("ftp://example.com/repo")
        assert is_valid is False
        assert "format" in error.lower()

    def test_repo_named_wiki_valid(self):
        """Repo with 'wiki' in name should be valid."""
        is_valid, error = validate_git_url("https://github.com/user/wiki-parser.git")
        assert is_valid is True

    def test_repo_named_blob_valid(self):
        """Repo with 'blob' in name should be valid."""
        is_valid, error = validate_git_url("https://github.com/user/blob-storage.git")
        assert is_valid is True
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_validators.py::TestValidateGitUrl -v`
Expected: FAIL with `ImportError`

**Step 3: Implement validate_git_url**

Add to `src/codogram/domain/validators.py`:

```python
import re

from .. import strings


def validate_git_url(url: str) -> tuple[bool, str | None]:
    """Validate git clone URL.

    Returns (is_valid, error_string). Uses precise GitHub patterns
    to avoid false positives on repos with names like 'wiki-parser'.
    """
    # GitHub-specific patterns (match only actual file/tree URLs)
    github_blob = re.compile(r'github\.com/[^/]+/[^/]+/blob/')
    github_tree = re.compile(r'github\.com/[^/]+/[^/]+/tree/')

    if "/wiki/" in url and "github.com" in url:
        return False, strings.GIT_URL_INVALID_WIKI
    if github_blob.search(url) or github_tree.search(url):
        return False, strings.GIT_URL_INVALID_BLOB
    if "gist.github.com" in url:
        return False, strings.GIT_URL_INVALID_GIST
    if not url.startswith(("https://", "git@", "ssh://")):
        return False, strings.GIT_URL_INVALID_FORMAT
    return True, None
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_validators.py::TestValidateGitUrl -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/domain/validators.py tests/test_validators.py && git commit -m "$(cat <<'EOF'
feat(validators): add validate_git_url() with GitHub-specific patterns

Validates git clone URLs and rejects:
- Wiki pages (/wiki/ in github.com URLs)
- File links (/blob/ or /tree/ in github.com URLs)
- Gists (gist.github.com)
- Invalid formats (not https://, git@, ssh://)

Uses precise regex to avoid false positives on repos named 'wiki-parser' etc.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update sanitize_project_name with unidecode

**Files:**
- Modify: `src/codogram/domain/validators.py`

**Step 1: Write the test**

```python
# tests/test_validators.py
from codogram.domain.validators import sanitize_project_name

class TestSanitizeProjectName:
    def test_cyrillic(self):
        result = sanitize_project_name("Мой Проект")
        assert result == "moj-proekt"

    def test_emoji(self):
        result = sanitize_project_name("Test Project 🚀")
        assert result == "test-project"

    def test_japanese(self):
        result = sanitize_project_name("日本語")
        # unidecode converts to romaji
        assert result is not None
        assert all(c.isalnum() or c == '-' for c in result)

    def test_already_valid(self):
        result = sanitize_project_name("my-project")
        assert result == "my-project"

    def test_spaces_to_dashes(self):
        result = sanitize_project_name("My Cool Project")
        assert result == "my-cool-project"

    def test_multiple_dashes_collapsed(self):
        result = sanitize_project_name("test---project")
        assert result == "test-project"

    def test_strips_leading_trailing_dashes(self):
        result = sanitize_project_name("-test-project-")
        assert result == "test-project"

    def test_empty_returns_none(self):
        result = sanitize_project_name("")
        assert result is None

    def test_too_long_returns_none(self):
        result = sanitize_project_name("a" * 100)
        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_validators.py::TestSanitizeProjectName -v`
Expected: FAIL (current implementation doesn't handle cyrillic)

**Step 3: Update sanitize_project_name**

Update in `src/codogram/domain/validators.py`:

```python
import re
from unidecode import unidecode


def sanitize_project_name(title: str) -> str | None:
    """Sanitize chat title to valid project name.

    Uses unidecode to transliterate non-ASCII characters.
    Returns None if result is empty or too long.
    """
    if not title:
        return None

    # Transliterate to ASCII
    sanitized = unidecode(title)
    sanitized = sanitized.lower()
    # Replace non-alphanumeric with dashes
    sanitized = re.sub(r'[^a-z0-9_-]', '-', sanitized)
    # Collapse multiple dashes
    sanitized = re.sub(r'-+', '-', sanitized)
    # Strip leading/trailing dashes
    sanitized = sanitized.strip('-')

    if not sanitized or len(sanitized) > 50:
        return None

    return sanitized
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_validators.py::TestSanitizeProjectName -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/domain/validators.py tests/test_validators.py && git commit -m "$(cat <<'EOF'
feat(validators): use unidecode in sanitize_project_name

Transliterate non-ASCII characters (cyrillic, CJK, etc.) to ASCII
before sanitizing. This allows chat titles like "Мой Проект" to
become "moj-proekt".

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add FlowAction.ASK_CLONE_URL_RETRY

**Files:**
- Modify: `src/codogram/services/start_flow.py`

**Step 1: Write the test**

```python
# tests/test_start_flow.py
from codogram.services.start_flow import FlowAction

def test_ask_clone_url_retry_action_exists():
    assert hasattr(FlowAction, 'ASK_CLONE_URL_RETRY')
    assert FlowAction.ASK_CLONE_URL_RETRY.value == "ask_clone_url_retry"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_ask_clone_url_retry_action_exists -v`
Expected: FAIL with `AttributeError`

**Step 3: Add the FlowAction**

Add to `FlowAction` enum in `src/codogram/services/start_flow.py` (after `ASK_CLONE_URL`):

```python
class FlowAction(Enum):
    # ... existing
    ASK_CLONE_URL = "ask_clone_url"
    ASK_CLONE_URL_RETRY = "ask_clone_url_retry"  # Shows error + re-prompt
    # ... rest
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_ask_clone_url_retry_action_exists -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/services/start_flow.py tests/test_start_flow.py && git commit -m "$(cat <<'EOF'
feat(start_flow): add ASK_CLONE_URL_RETRY action

New FlowAction for URL validation errors that keeps FSM state
so user can retry without restarting the flow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update handle_clone_url() to use validation

**Note:** This task uses `git_clone()` which already exists in `project_launcher.py`. Task 8 later improves it with cleanup-on-failure.

**Files:**
- Modify: `src/codogram/services/start_flow.py`

**Step 1: Write the test**

```python
# tests/test_start_flow.py
from unittest.mock import MagicMock
from codogram.services.start_flow import StartFlowService, FlowAction

def test_handle_clone_url_validates_wiki_url():
    pm = MagicMock()
    service = StartFlowService(pm, None)

    result = service.handle_clone_url(
        chat_id=123,
        project="test",
        path="/tmp/test",
        url="https://github.com/user/repo/wiki/Page"
    )

    assert result.action == FlowAction.ASK_CLONE_URL_RETRY
    assert "wiki" in result.error.lower()

def test_handle_clone_url_validates_blob_url():
    pm = MagicMock()
    service = StartFlowService(pm, None)

    result = service.handle_clone_url(
        chat_id=123,
        project="test",
        path="/tmp/test",
        url="https://github.com/user/repo/blob/main/file.py"
    )

    assert result.action == FlowAction.ASK_CLONE_URL_RETRY
    assert "file" in result.error.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_handle_clone_url_validates_wiki_url tests/test_start_flow.py::test_handle_clone_url_validates_blob_url -v`
Expected: FAIL (returns ERROR not ASK_CLONE_URL_RETRY)

**Step 3: Update handle_clone_url()**

Update in `src/codogram/services/start_flow.py`:

```python
from ..domain.validators import validate_git_url

def handle_clone_url(
    self, chat_id: int, project: str, path: str, url: str
) -> FlowResult:
    """Handle user input for git clone URL."""
    # Validate URL format
    is_valid, error_msg = validate_git_url(url)
    if not is_valid:
        return FlowResult(
            action=FlowAction.ASK_CLONE_URL_RETRY,
            error=error_msg,
            project=project,
            path=path,
        )

    result = git_clone(path, url)

    if not result.success:
        return FlowResult(
            action=FlowAction.ASK_CLONE_URL_RETRY,
            error=f"Clone failed: {result.error}",
            project=project,
            path=path,
        )

    proj = self.pm.get_or_create(project)
    proj.chat_id = chat_id
    proj.cwd = path
    self.pm._save()

    return FlowResult(
        action=FlowAction.LAUNCH,
        project=project,
        path=path,
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_handle_clone_url_validates_wiki_url tests/test_start_flow.py::test_handle_clone_url_validates_blob_url -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/services/start_flow.py tests/test_start_flow.py && git commit -m "$(cat <<'EOF'
feat(start_flow): validate URLs before git clone

Use validate_git_url() to check URLs before attempting clone.
Return ASK_CLONE_URL_RETRY on validation failure so user can
correct the URL without restarting the flow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Handle ASK_CLONE_URL_RETRY in start.py handler

**Files:**
- Modify: `src/codogram/handlers/start.py`

**Step 1: Write the test**

This is a handler test - manual E2E testing is more appropriate. Skip unit test for handler logic.

**Step 2: Show progress message before clone**

In the handler that processes `StartFlow.awaiting_clone_url` state (where user sends URL), add progress message BEFORE calling service:

```python
# In the awaiting_clone_url handler, before calling handle_clone_url:
await telegram_queue.reply(message, strings.CLONE_IN_PROGRESS)

# Then call service
result = start_flow_service.handle_clone_url(...)
```

**Step 3: Add handler case**

Add to `_handle_result()` in `src/codogram/handlers/start.py`:

```python
case FlowAction.ASK_CLONE_URL_RETRY:
    # Stay in awaiting_clone_url state - don't clear, let user retry
    await telegram_queue.reply(
        message,
        f"{result.error}\n\n{strings.GIT_URL_RETRY_PROMPT}",
    )
```

Add to `_handle_callback_result()` for callback context:

```python
case FlowAction.ASK_CLONE_URL_RETRY:
    # Stay in awaiting_clone_url state - don't clear, let user retry
    await telegram_queue.edit(
        callback.message,
        f"{result.error}\n\n{strings.GIT_URL_RETRY_PROMPT}",
    )
```

**Step 4: Test manually**

Run bot with `./dev-run.sh` and test:
1. Start new project flow
2. Choose clone option
3. Enter invalid URL (wiki, blob, gist)
4. Verify error shown with retry prompt
5. Enter another invalid URL
6. Verify can keep retrying (no limit)
7. Enter valid URL
8. Verify "Cloning..." progress message shown
9. Verify clone proceeds

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/handlers/start.py && git commit -m "$(cat <<'EOF'
feat(handlers/start): handle ASK_CLONE_URL_RETRY action

Show error message + retry prompt without clearing FSM state.
User can correct URL and try again.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add git_clone() cleanup on failure

**Note:** `git_clone()` already exists. This task adds cleanup behavior on failure. User can cancel with /cancel.

**Files:**
- Modify: `src/codogram/project_launcher.py` (update existing `git_clone` function)

**Step 1: Write the test**

```python
# tests/test_project_launcher.py
import tempfile
from pathlib import Path
from codogram.project_launcher import git_clone

def test_git_clone_cleans_up_on_failure():
    """git_clone should remove partial directory on failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "test-repo"

        # Clone from invalid URL - should fail
        result = git_clone(str(target), "https://invalid-url-that-does-not-exist.com/repo.git")

        assert result.success is False
        # Directory should NOT exist after failed clone
        assert not target.exists(), "Failed clone should clean up directory"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_project_launcher.py::test_git_clone_cleans_up_on_failure -v`
Expected: FAIL (directory exists after failed clone)

**Step 3: Update git_clone()**

Update in `src/codogram/project_launcher.py`:

```python
import shutil

def git_clone(path: str, repo_url: str) -> LaunchResult:
    """Clone repository into path. Cleans up on failure."""
    target = Path(path)
    try:
        parent = str(target.parent)
        name = target.name

        # Ensure parent exists
        target.parent.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["git", "clone", repo_url, name],
            cwd=parent,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Cleanup partial clone
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            return LaunchResult(success=False, error=result.stderr.strip())

        return LaunchResult(success=True)
    except Exception as e:
        # Cleanup on exception
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        return LaunchResult(success=False, error=str(e))
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_project_launcher.py::test_git_clone_cleans_up_on_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/project_launcher.py tests/test_project_launcher.py && git commit -m "$(cat <<'EOF'
fix(project_launcher): cleanup directory on git clone failure

Remove partial directory if clone fails, preventing broken state
where project directory exists but is incomplete.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Add file locking to ProjectManager._save()

**Files:**
- Modify: `src/codogram/session_manager.py`

**Step 1: Write the test**

```python
# tests/test_session_manager.py
import threading
import time
from codogram.session_manager import ProjectManager

def test_save_is_thread_safe():
    """Multiple saves should not corrupt config."""
    pm = ProjectManager()

    errors = []

    def save_project(name):
        try:
            for _ in range(10):
                p = pm.get_or_create(name)
                p.chat_id = hash(name) % 1000000
                pm._save()
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=save_project, args=(f"project-{i}",))
        for i in range(5)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Save errors: {errors}"
```

**Step 2: Run test to verify behavior**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_session_manager.py::test_save_is_thread_safe -v`
Expected: May pass or fail randomly without locking

**Step 3: Add file locking**

Update `_save()` in `src/codogram/session_manager.py`:

```python
import fcntl
import json
from .config import get_config_path

def _save(self) -> None:
    """Persist to disk with file locking."""
    config_path = get_config_path()

    # Ensure file exists
    if not config_path.exists():
        config_path.write_text("{}")

    with open(config_path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # Read current state
            f.seek(0)
            try:
                current = json.load(f)
            except json.JSONDecodeError:
                current = {}

            # Build projects data
            projects_data = {}
            for name, p in self.projects.items():
                if p.chat_id is None:
                    continue
                project_data = {"chat_id": p.chat_id, "cwd": p.cwd, "auto_accept": p.auto_accept}

                # Backward compat: duplicate threads[None] to legacy fields
                if None in p.threads:
                    main_thread = p.threads[None]
                    project_data["session_id"] = main_thread.session_id
                    project_data["jsonl_path"] = main_thread.jsonl_path

                # Save all threads with full state
                if p.threads:
                    threads_dict = {}
                    for tid, t in p.threads.items():
                        thread_data = {
                            "name": t.name,
                            "topic_name": t.topic_name,
                            "session_id": t.session_id,
                            "jsonl_path": t.jsonl_path,
                            "awaiting_new_session": t.awaiting_new_session,
                            "start_requested_at": t.start_requested_at,
                        }
                        # Worktree fields - only save if set
                        if t.worktree_path:
                            thread_data["worktree_path"] = t.worktree_path
                        if t.base_branch:
                            thread_data["base_branch"] = t.base_branch
                        if t.archived:
                            thread_data["archived"] = t.archived
                        if t.auto_accept:
                            thread_data["auto_accept"] = t.auto_accept
                        threads_dict[str(tid) if tid is not None else "null"] = thread_data
                    project_data["threads"] = threads_dict
                projects_data[name] = project_data

            # Update config
            current["projects"] = projects_data
            current.pop("sessions", None)

            # Write back
            f.seek(0)
            f.truncate()
            json.dump(current, f, indent=2)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

Also need to add `get_config_path()` to config.py if not exists, or import from config.

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_session_manager.py::test_save_is_thread_safe -v`
Expected: PASS consistently

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/session_manager.py tests/test_session_manager.py && git commit -m "$(cat <<'EOF'
feat(session_manager): add file locking to _save()

Use fcntl.flock() for exclusive locking during config save.
Prevents race conditions when multiple /start commands run
concurrently.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Implement is_setup_phase()

**Files:**
- Modify: `src/codogram/services/start_flow.py`

**Step 1: Write the test**

```python
# tests/test_start_flow.py
from unittest.mock import MagicMock
from codogram.services.start_flow import is_setup_phase
from codogram.session_manager import ProjectState, ThreadInfo

def test_is_setup_phase_no_threads():
    project = ProjectState(project_name="test")
    assert is_setup_phase(project) is True

def test_is_setup_phase_main_thread_no_session():
    project = ProjectState(project_name="test")
    project.threads[None] = ThreadInfo(thread_id=None, name="main")
    assert is_setup_phase(project) is True

def test_is_setup_phase_main_thread_with_session():
    project = ProjectState(project_name="test")
    project.threads[None] = ThreadInfo(thread_id=None, name="main", session_id="abc123")
    assert is_setup_phase(project) is False

def test_is_setup_phase_legacy_session_id():
    """Legacy projects have session_id on project, not thread."""
    project = ProjectState(project_name="test")
    project.session_id = "legacy-session"
    assert is_setup_phase(project) is False
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_is_setup_phase_no_threads tests/test_start_flow.py::test_is_setup_phase_main_thread_no_session tests/test_start_flow.py::test_is_setup_phase_main_thread_with_session tests/test_start_flow.py::test_is_setup_phase_legacy_session_id -v`
Expected: FAIL with `ImportError`

**Step 3: Implement is_setup_phase()**

Add to `src/codogram/services/start_flow.py`:

```python
def is_setup_phase(project: "ProjectState") -> bool:
    """Check if project is in setup phase (Claude never ran).

    Returns True if no session ever started in main thread.
    Handles legacy projects that have session_id on project instead of thread.
    """
    # Check new threads structure
    main_thread = project.threads.get(None)
    if main_thread and main_thread.session_id:
        return False

    # Fallback: legacy session_id field
    if project.session_id:
        return False

    return True
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_is_setup_phase_no_threads tests/test_start_flow.py::test_is_setup_phase_main_thread_no_session tests/test_start_flow.py::test_is_setup_phase_main_thread_with_session tests/test_start_flow.py::test_is_setup_phase_legacy_session_id -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/services/start_flow.py tests/test_start_flow.py && git commit -m "$(cat <<'EOF'
feat(start_flow): add is_setup_phase() helper

Check if project is in setup phase (Claude never ran).
Handles both new threads structure and legacy session_id field.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Implement require_tmux_exists() and require_claude_ready()

**Files:**
- Modify: `src/codogram/handlers/common.py` (add new helpers after existing `require_forum_group`)

**Step 1: Write the test**

```python
# tests/test_handlers_common.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from codogram.handlers.common import require_tmux_exists, require_claude_ready

@pytest.mark.asyncio
async def test_require_tmux_exists_no_project():
    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    with patch('codogram.handlers.common.project_manager') as pm:
        pm.get_by_chat.return_value = None

        result = await require_tmux_exists(message, queue)

        assert result is False
        queue.reply.assert_called_once()

@pytest.mark.asyncio
async def test_require_claude_ready_tmux_not_ready():
    message = MagicMock()
    message.chat.id = 123
    message.message_thread_id = None
    queue = AsyncMock()

    project = MagicMock()
    project.cwd = "/test"
    project.project_name = "test"
    thread = MagicMock()
    thread.get_tmux_session.return_value = "claude-test"
    project.threads = {None: thread}

    with patch('codogram.handlers.common.project_manager') as pm, \
         patch('codogram.handlers.common.is_tmux_session_exists') as tmux_exists, \
         patch('codogram.handlers.common.TmuxSession') as TmuxClass:

        pm.get_by_chat.return_value = project
        tmux_exists.return_value = True
        tmux_instance = MagicMock()
        tmux_instance.is_claude_ready.return_value = False
        TmuxClass.return_value = tmux_instance

        result = await require_claude_ready(message, queue)

        assert result is False
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_handlers_common.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement helpers**

Add to `src/codogram/handlers/common.py` (after existing `require_forum_group` function):

```python
# Add imports at top of file:
from ..session_manager import project_manager
from ..project_launcher import is_tmux_session_exists
from ..tmux import TmuxSession

# Add after require_forum_group function:

async def require_tmux_exists(
    message: Message, telegram_queue: TelegramQueue
) -> bool:
    """Check: project + cwd + tmux session exists.

    Use for commands that work during startup: /clear, /esc
    """
    project = project_manager.get_by_chat(message.chat.id)
    if not project or not project.cwd:
        await telegram_queue.reply(message, strings.PROJECT_NOT_READY)
        return False

    thread = project.threads.get(message.message_thread_id)
    if not thread:
        await telegram_queue.reply(message, strings.PROJECT_NOT_READY)
        return False

    tmux_name = thread.get_tmux_session(project.project_name)
    if not is_tmux_session_exists(tmux_name):
        await telegram_queue.reply(message, strings.CLAUDE_NOT_RUNNING)
        return False

    return True


async def require_claude_ready(
    message: Message, telegram_queue: TelegramQueue
) -> bool:
    """Strict check: project + cwd + tmux + Claude ready.

    Use for commands that need Claude running: /new, /thread, /branch, /finish
    """
    if not await require_tmux_exists(message, telegram_queue):
        return False

    # Additional check: Claude is ready (not starting)
    project = project_manager.get_by_chat(message.chat.id)
    thread = project.threads.get(message.message_thread_id)
    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    if not tmux.is_claude_ready():
        await telegram_queue.reply(message, strings.CLAUDE_STARTING)
        return False

    return True
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_handlers_common.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/handlers/common.py tests/test_handlers_common.py && git commit -m "$(cat <<'EOF'
feat(handlers/common): add require_tmux_exists() and require_claude_ready()

Two-level project ready checks:
- require_tmux_exists(): for /clear, /esc (work during startup)
- require_claude_ready(): for /new, /thread, /branch, /finish

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Update handlers to use require_* helpers

**Files:**
- Modify: `src/codogram/handlers/sessions.py`
- Modify: `src/codogram/handlers/threads.py`
- Modify: `src/codogram/handlers/branches.py`
- Modify: `src/codogram/handlers/finish.py`

**Step 1: No unit test needed**

Handler integration - manual E2E testing.

**Step 2: Update sessions.py**

Add to top:
```python
from .common import require_tmux_exists, require_claude_ready
```

Update `/clear` and `/esc` handlers:
```python
@router.message(Command("clear"))
async def cmd_clear(message: Message, ...):
    if not await require_tmux_exists(message, telegram_queue):
        return
    # ... existing logic

@router.message(Command("esc"))
async def cmd_esc(message: Message, ...):
    if not await require_tmux_exists(message, telegram_queue):
        return
    # ... existing logic
```

Update `/new` handler:
```python
@router.message(Command("new"))
async def cmd_new(message: Message, ...):
    if not await require_claude_ready(message, telegram_queue):
        return
    # ... existing logic
```

**Step 3: Update threads.py**

Add import and update `/thread` handler:
```python
from .common import require_claude_ready

@router.message(Command("thread"))
async def cmd_thread(message: Message, ...):
    if not await require_claude_ready(message, telegram_queue):
        return
    # ... existing logic
```

**Step 4: Update branches.py**

Add import and update `/branch` handler:
```python
from .common import require_claude_ready

@router.message(Command("branch"))
async def cmd_branch(message: Message, ...):
    if not await require_claude_ready(message, telegram_queue):
        return
    # ... existing logic
```

**Step 5: Update finish.py**

Add import and update `/finish` handler:
```python
from .common import require_claude_ready

@router.message(Command("finish"))
async def cmd_finish(message: Message, ...):
    if not await require_claude_ready(message, telegram_queue):
        return
    # ... existing logic
```

**Step 6: Test manually**

Run bot and verify:
1. Without project → /clear shows "Project not ready"
2. With tmux but Claude starting → /new shows "Claude is starting..."
3. With Claude ready → commands work normally

**Step 7: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/handlers/sessions.py src/codogram/handlers/threads.py src/codogram/handlers/branches.py src/codogram/handlers/finish.py && git commit -m "$(cat <<'EOF'
feat(handlers): use require_* helpers for project state checks

- /clear, /esc: require_tmux_exists()
- /new, /thread, /branch, /finish: require_claude_ready()

Ensures commands show appropriate messages when project not ready.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Create reset keyboards

**Files:**
- Create: `src/codogram/keyboards/reset.py`

**Step 1: Write the test**

```python
# tests/test_keyboards_reset.py
from codogram.keyboards.reset import (
    reset_confirm_keyboard,
    reset_dir_choice_keyboard,
    reset_uncommitted_keyboard,
)

def test_reset_confirm_keyboard():
    kb = reset_confirm_keyboard()
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "Continue" in buttons
    assert "Cancel" in buttons

def test_reset_dir_choice_keyboard():
    kb = reset_dir_choice_keyboard()
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "Keep directory" in buttons or "Keep" in buttons
    assert "Delete" in buttons
    assert "[<<] Go back" in buttons

def test_reset_uncommitted_keyboard():
    kb = reset_uncommitted_keyboard()
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "Keep directory" in buttons
    assert "Delete anyway" in buttons
    assert "[<<] Go back" in buttons
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_keyboards_reset.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement keyboards**

Create `src/codogram/keyboards/reset.py`:

```python
"""Keyboards for /reset_all flow."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import strings


def reset_confirm_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for reset confirmation step."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_CONTINUE, callback_data="reset:continue"),
            InlineKeyboardButton(text=strings.BTN_CANCEL, callback_data="reset:cancel"),
        ],
    ])


def reset_dir_choice_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for directory choice step."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_KEEP_DIR, callback_data="reset:keep"),
            InlineKeyboardButton(text=strings.BTN_DELETE_DIR, callback_data="reset:delete"),
        ],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="reset:back")],
    ])


def reset_uncommitted_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for uncommitted changes warning."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=strings.BTN_KEEP_DIR, callback_data="reset:keep"),
            InlineKeyboardButton(text=strings.BTN_DELETE_ANYWAY, callback_data="reset:delete"),
        ],
        [InlineKeyboardButton(text=strings.BTN_GO_BACK, callback_data="reset:back")],
    ])
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_keyboards_reset.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/keyboards/reset.py tests/test_keyboards_reset.py && git commit -m "$(cat <<'EOF'
feat(keyboards): add reset flow keyboards

Add reset_confirm_keyboard, reset_dir_choice_keyboard, and
reset_uncommitted_keyboard for /reset_all multi-step flow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Verify existing has_uncommitted_changes()

**Note:** `has_uncommitted_changes(repo_path: Path)` already exists in `git_utils.py:71`. This task verifies existing tests or adds tests if missing.

**Files:**
- Verify: `src/codogram/git_utils.py` (function exists at line 71)
- Modify: `tests/test_git_utils.py` (add tests if missing)

**Step 1: Check if tests exist**

Run: `cd /home/superbereza/dev/codogram && grep -l "has_uncommitted_changes" tests/`

**Step 2: If no tests exist, write them**

```python
# tests/test_git_utils.py
import tempfile
import subprocess
from pathlib import Path
from codogram.git_utils import has_uncommitted_changes

def test_has_uncommitted_changes_clean_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        (path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        assert has_uncommitted_changes(path) is False  # Note: takes Path, not str

def test_has_uncommitted_changes_with_changes():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        (path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)

        (path / "file.txt").write_text("changed")

        assert has_uncommitted_changes(path) is True  # Note: takes Path, not str
```

**Step 3: Run tests**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_git_utils.py -v -k has_uncommitted`
Expected: PASS

**Step 4: Commit (if tests added)**

```bash
cd /home/superbereza/dev/codogram && git add tests/test_git_utils.py && git commit -m "$(cat <<'EOF'
test(git_utils): add tests for existing has_uncommitted_changes

Verify existing function works as expected.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Add ResetFlow FSM states

**Files:**
- Modify: `src/codogram/domain/states.py`

**Step 1: Write the test**

```python
# tests/test_states.py
from codogram.domain.states import ResetFlow

def test_reset_flow_states_exist():
    assert hasattr(ResetFlow, 'awaiting_confirm')
    assert hasattr(ResetFlow, 'awaiting_dir_choice')
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_states.py::test_reset_flow_states_exist -v`
Expected: FAIL with `AttributeError`

**Step 3: Add ResetFlow states**

Add to `src/codogram/domain/states.py`:

```python
from aiogram.fsm.state import State, StatesGroup


class ResetFlow(StatesGroup):
    """FSM states for /reset_all flow."""
    awaiting_confirm = State()
    awaiting_dir_choice = State()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_states.py::test_reset_flow_states_exist -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/domain/states.py tests/test_states.py && git commit -m "$(cat <<'EOF'
feat(states): add ResetFlow FSM states

Add awaiting_confirm and awaiting_dir_choice states for
/reset_all multi-step flow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Add cleanup_project() helper

**Files:**
- Modify: `src/codogram/services/start_flow.py`

**Step 1: Write the test**

```python
# tests/test_start_flow.py
from unittest.mock import MagicMock, patch
from codogram.services.start_flow import cleanup_project
from codogram.session_manager import ProjectState, ThreadInfo

def test_cleanup_project_kills_tmux():
    project = ProjectState(project_name="test", cwd="/test/path")
    project.threads[None] = ThreadInfo(thread_id=None, name="main")
    project.threads[123] = ThreadInfo(thread_id=123, name="feature")

    with patch('codogram.services.start_flow.is_tmux_session_exists') as exists, \
         patch('codogram.services.start_flow.kill_tmux_session') as kill, \
         patch('codogram.services.start_flow.project_manager') as pm:

        exists.return_value = True

        result = cleanup_project(project, delete_directory=False)

        # Should kill tmux for both threads
        assert kill.call_count == 2
        assert result.success is True


def test_cleanup_project_reports_failed_deletion():
    """cleanup_project should report if directory deletion fails."""
    project = ProjectState(project_name="test", cwd="/nonexistent/protected/path")
    project.threads[None] = ThreadInfo(thread_id=None, name="main")

    with patch('codogram.services.start_flow.is_tmux_session_exists') as exists, \
         patch('codogram.services.start_flow.kill_tmux_session') as kill, \
         patch('codogram.services.start_flow.project_manager') as pm, \
         patch('codogram.services.start_flow.Path') as MockPath:

        exists.return_value = False
        # Simulate directory still exists after rmtree
        MockPath.return_value.exists.return_value = True

        result = cleanup_project(project, delete_directory=True)

        assert result.success is False
        assert "Could not delete" in result.error
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_cleanup_project_kills_tmux -v`
Expected: FAIL with `ImportError`

**Step 3: Implement cleanup_project()**

Add to `src/codogram/services/start_flow.py`:

```python
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass

from .. import strings


@dataclass
class CleanupResult:
    success: bool
    error: str | None = None


def cleanup_project(project: "ProjectState", delete_directory: bool) -> CleanupResult:
    """Full project cleanup.

    Args:
        project: Project to cleanup
        delete_directory: Whether to delete the project directory

    Returns:
        CleanupResult with success=False if directory deletion failed
    """
    # 1. Kill all tmux sessions (main + topics)
    for thread in project.threads.values():
        tmux_name = thread.get_tmux_session(project.project_name)
        if is_tmux_session_exists(tmux_name):
            kill_tmux_session(tmux_name)

    # 2. Remove worktrees (if any)
    if project.cwd:
        for thread in project.threads.values():
            if thread.worktree_path:
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", thread.worktree_path],
                        cwd=project.cwd,
                        capture_output=True,
                    )
                except Exception:
                    pass  # Best effort

    # 3. Delete main directory (if requested)
    cleanup_failed = False
    if delete_directory and project.cwd:
        shutil.rmtree(project.cwd, ignore_errors=True)
        # Verify deletion succeeded
        if Path(project.cwd).exists():
            cleanup_failed = True

    # 4. Remove from config
    from ..session_manager import project_manager
    if project.project_name in project_manager.projects:
        del project_manager.projects[project.project_name]
        project_manager._save()

    if cleanup_failed:
        return CleanupResult(
            success=False,
            error=strings.RESET_CLEANUP_FAILED.format(path=project.cwd)
        )
    return CleanupResult(success=True)
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_cleanup_project_kills_tmux -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/services/start_flow.py tests/test_start_flow.py && git commit -m "$(cat <<'EOF'
feat(start_flow): add cleanup_project() helper

Full project cleanup: kill tmux sessions, remove worktrees,
optionally delete directory, remove from config.

Used by /reset_all flow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Implement /reset_all command handler

**Files:**
- Modify: `src/codogram/handlers/start.py`

**Step 1: No unit test**

Complex handler flow - manual E2E testing.

**Step 2: Add imports**

Add to `src/codogram/handlers/start.py`:

```python
from pathlib import Path
from ..domain.states import StartFlow, RestartFlow, ResetFlow
from ..keyboards.reset import reset_confirm_keyboard, reset_dir_choice_keyboard, reset_uncommitted_keyboard
from ..services.start_flow import is_setup_phase, cleanup_project
from ..git_utils import has_uncommitted_changes
```

**Step 3: Add /reset_all command**

```python
@router.message(Command("reset_all"))
async def cmd_reset_all(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle /reset_all command."""
    # Check if start flow is in progress (e.g., clone running)
    current_state = await state.get_state()
    if current_state and str(current_state).startswith("StartFlow:"):
        await telegram_queue.reply(message, strings.RESET_FLOW_IN_PROGRESS)
        return

    project = project_manager.get_by_chat(message.chat.id)

    # No project registered
    if not project:
        await telegram_queue.reply(message, strings.RESET_NO_PROJECT)
        return

    # Setup phase - reset immediately
    if is_setup_phase(project):
        result = cleanup_project(project, delete_directory=True)
        if result.success:
            await telegram_queue.reply(message, strings.RESET_COMPLETE)
        else:
            await telegram_queue.reply(message, result.error)
        return

    # Working project - ask for confirmation
    await state.set_state(ResetFlow.awaiting_confirm)
    await state.update_data(project_name=project.project_name)

    # Different message if called from topic
    if message.message_thread_id:
        text = strings.RESET_CONFIRM_TOPIC.format(name=project.project_name)
    else:
        text = strings.RESET_CONFIRM.format(name=project.project_name)

    await telegram_queue.reply(message, text, reply_markup=reset_confirm_keyboard())
```

**Step 4: Add reset flow callbacks**

```python
@router.callback_query(F.data == "reset:continue")
async def on_reset_continue(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset confirm → continue."""
    # Verify we're in the right state
    current_state = await state.get_state()
    if current_state != ResetFlow.awaiting_confirm:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    data = await state.get_data()
    project_name = data.get("project_name")
    if not project_name:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    project = project_manager.projects.get(project_name)
    if not project or not project.cwd:
        # No directory to worry about
        cleanup_project(project, delete_directory=False)
        await state.clear()
        await telegram_queue.edit(
            callback.message,
            strings.RESET_DONE.format(dir_status="not found"),
        )
        await callback.answer()
        return

    # Directory exists - check for uncommitted changes
    await state.set_state(ResetFlow.awaiting_dir_choice)

    if has_uncommitted_changes(Path(project.cwd)):  # Note: Path() required
        await telegram_queue.edit(
            callback.message,
            strings.RESET_UNCOMMITTED.format(path=project.cwd),
            reply_markup=reset_uncommitted_keyboard(),
        )
    else:
        await telegram_queue.edit(
            callback.message,
            strings.RESET_DIR_CHOICE.format(path=project.cwd),
            reply_markup=reset_dir_choice_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "reset:keep")
async def on_reset_keep(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset → keep directory."""
    # Verify we're in the right state
    current_state = await state.get_state()
    if current_state != ResetFlow.awaiting_dir_choice:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    data = await state.get_data()
    project_name = data.get("project_name")
    if not project_name:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    project = project_manager.projects.get(project_name)
    if not project:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    cleanup_project(project, delete_directory=False)

    await state.clear()
    await telegram_queue.edit(
        callback.message,
        strings.RESET_DONE.format(dir_status=f"kept at `{project.cwd}`"),
    )
    await callback.answer()


@router.callback_query(F.data == "reset:delete")
async def on_reset_delete(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset → delete directory."""
    # Verify we're in the right state
    current_state = await state.get_state()
    if current_state != ResetFlow.awaiting_dir_choice:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    data = await state.get_data()
    project_name = data.get("project_name")
    if not project_name:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    project = project_manager.projects.get(project_name)
    if not project:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    result = cleanup_project(project, delete_directory=True)

    await state.clear()

    # Show error if cleanup failed, otherwise success
    if result.success:
        await telegram_queue.edit(
            callback.message,
            strings.RESET_DONE.format(dir_status="deleted"),
        )
    else:
        await telegram_queue.edit(callback.message, result.error)
    await callback.answer()




@router.callback_query(F.data == "reset:back")
async def on_reset_back(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset → go back."""
    # Verify we're in the right state
    current_state = await state.get_state()
    if current_state != ResetFlow.awaiting_dir_choice:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    data = await state.get_data()
    project_name = data.get("project_name")
    if not project_name:
        await callback.answer(strings.SESSION_EXPIRED)
        return

    # Go back to confirm step
    await state.set_state(ResetFlow.awaiting_confirm)

    text = strings.RESET_CONFIRM.format(name=project_name)
    await telegram_queue.edit(
        callback.message,
        text,
        reply_markup=reset_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "reset:cancel")
async def on_reset_cancel(callback: CallbackQuery, state: FSMContext, telegram_queue: TelegramQueue):
    """Handle reset → cancel."""
    await state.clear()
    await telegram_queue.edit(callback.message, strings.CANCELLED, parse_mode=None)
    await callback.answer()
```

**Step 5: Test manually**

Run bot and test:
1. /reset_all without project → "Nothing to reset"
2. /reset_all in setup phase → immediate reset
3. /reset_all with project → confirm → dir choice → keep/delete
4. Test go back button at each step
5. Test cancel button

**Step 6: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/handlers/start.py && git commit -m "$(cat <<'EOF'
feat(handlers/start): implement /reset_all command

Multi-step flow with:
- No project → "Nothing to reset"
- Setup phase → immediate reset
- Working project → confirm → dir choice (with uncommitted warning)
- Go back buttons at each step
- Cancel option throughout

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Add build_announcement() helper

**Files:**
- Modify: `src/codogram/services/start_flow.py`

**Step 1: Write the test**

```python
# tests/test_start_flow.py
from codogram.services.start_flow import build_announcement

def test_build_announcement_non_forum():
    result = build_announcement("test-project", "claude-test", is_forum=False)

    assert "test-project" in result
    assert "claude-test" in result
    assert "/esc" in result
    assert "/clear" in result
    assert "/auto_accept" in result
    assert "/thread" not in result  # Forum-only
    assert "/branch" not in result
    assert "/finish" not in result

def test_build_announcement_forum():
    result = build_announcement("test-project", "claude-test", is_forum=True)

    assert "/thread" in result
    assert "/branch" in result
    assert "/finish" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_build_announcement_non_forum tests/test_start_flow.py::test_build_announcement_forum -v`
Expected: FAIL with `ImportError`

**Step 3: Implement build_announcement()**

Add to `src/codogram/services/start_flow.py`:

```python
def build_announcement(project_name: str, tmux_name: str, is_forum: bool) -> str:
    """Build project ready announcement message.

    Args:
        project_name: Name of the project
        tmux_name: Name of the tmux session
        is_forum: Whether chat is a forum (has topics)

    Returns:
        Formatted announcement message
    """
    commands = [
        "• /esc — cancel operation",
        "• /clear — clear context",
        "• /auto_accept — toggle auto-accept",
    ]
    if is_forum:
        commands.extend([
            "• /thread — new topic",
            "• /branch — new branch + topic",
            "• /finish — merge and archive",
        ])

    return f"""`[v]` Project `{project_name}` ready

Commands available in this chat:
{chr(10).join(commands)}

To see Claude's UI, run in terminal:
`tmux attach -t {tmux_name}`"""
```

**Step 4: Run test to verify it passes**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_start_flow.py::test_build_announcement_non_forum tests/test_start_flow.py::test_build_announcement_forum -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/services/start_flow.py tests/test_start_flow.py && git commit -m "$(cat <<'EOF'
feat(start_flow): add build_announcement() helper

Build project ready message with available commands.
Forum chats show /thread, /branch, /finish; non-forum chats don't.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: Use build_announcement() in launch success

**Files:**
- Modify: `src/codogram/launch_animation.py` (or wherever success message is sent)

**Step 1: No unit test**

Integration - manual E2E testing.

**Step 2: Find and update success message**

Locate where `LAUNCH_READY` or similar is sent after successful launch. Update to use `build_announcement()`.

Example update in `launch_animation.py`:

```python
from .services.start_flow import build_announcement

# After launch completes successfully:
if is_forum is not None:
    announcement = build_announcement(project.project_name, tmux_name, is_forum)
    await queue.send(chat_id, announcement, thread_id=thread_id)
```

**Step 3: Test manually**

Run bot and verify:
1. Launch project in non-forum chat → shows basic commands
2. Launch project in forum chat → shows full command list including /thread, /branch, /finish

**Step 4: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/launch_animation.py && git commit -m "$(cat <<'EOF'
feat(launch_animation): use build_announcement() for success message

Show available commands after successful project launch.
Commands vary based on chat type (forum vs non-forum).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 20: E2E Tests

**Files:**
- Create/Modify: `docs/e2e/commands/start.md`

**Step 1: Add E2E test cases**

Add to `docs/e2e/commands/start.md`:

```markdown
## URL Validation Tests

### Test: Wiki URL rejected
1. Start new project flow, choose clone
2. Enter: `https://github.com/user/repo/wiki/Page`
3. Expected: Error "This is a wiki page, not a repository" + retry prompt
4. Enter valid URL
5. Expected: Clone proceeds

### Test: Blob URL rejected
1. Start new project flow, choose clone
2. Enter: `https://github.com/user/repo/blob/main/file.py`
3. Expected: Error "This is a file link" + retry prompt

### Test: Repo named wiki-parser valid
1. Start new project flow, choose clone
2. Enter: `https://github.com/user/wiki-parser.git`
3. Expected: Clone proceeds (no false positive)

## /reset_all Tests

### Test: No project
1. /reset_all in chat without project
2. Expected: "Nothing to reset. Use /start to begin."

### Test: Setup phase
1. /start, enter project name, but don't complete setup
2. /reset_all
3. Expected: Immediate reset, "Reset complete"

### Test: Working project with clean directory
1. Setup project fully
2. /reset_all
3. Click Continue
4. Expected: Directory choice prompt
5. Click Keep
6. Expected: "Directory kept at..."

### Test: Working project with uncommitted changes
1. Setup project, make uncommitted changes
2. /reset_all
3. Click Continue
4. Expected: "Uncommitted changes" warning
5. Click Delete anyway
6. Expected: "Directory deleted"

### Test: Go back
1. /reset_all on working project
2. Click Continue
3. Click [<<] Go back
4. Expected: Back to confirm step

## Project Ready Checks

### Test: /clear without project
1. /clear in chat without project
2. Expected: "Project not ready. Use /start first"

### Test: /new while Claude starting
1. Start project, immediately run /new before Claude ready
2. Expected: "Claude is starting... wait a moment"
```

**Step 2: Run E2E tests manually**

Use Telegram MCP to run through each test case.

**Step 3: Commit**

```bash
cd /home/superbereza/dev/codogram && git add docs/e2e/commands/start.md && git commit -m "$(cat <<'EOF'
docs(e2e): add robust start flow test cases

Add E2E tests for:
- URL validation (wiki, blob, gist, false positives)
- /reset_all flow (setup phase, working project, uncommitted changes)
- Project ready checks (/clear, /new timing)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements the robust /start flow design in 20 tasks:

1. **Tasks 1-2**: Add strings for URL validation, project state, reset flow
2. **Tasks 3-4**: Implement validate_git_url() and update sanitize_project_name with unidecode
3. **Tasks 5-7**: Add ASK_CLONE_URL_RETRY action and use validation in clone flow
4. **Task 8**: Add git_clone() cleanup on failure
5. **Task 9**: Add file locking to ProjectManager._save()
6. **Task 10**: Implement is_setup_phase()
7. **Tasks 11-12**: Implement require_tmux_exists() and require_claude_ready(), update handlers
8. **Tasks 13-17**: Implement /reset_all flow (keyboards, FSM states, helpers, handler)
9. **Tasks 18-19**: Add build_announcement() and use it in launch success
10. **Task 20**: E2E tests

Total estimated commits: 20
