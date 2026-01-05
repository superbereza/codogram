# Phase 7b: Thread/Topic Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend `StartFlowService` with `thread_id` parameter to handle topic-specific /start flow

**Architecture:** Add `thread_id` to `handle_start()` signature. When `thread_id` is provided, delegate to `_handle_topic_start()` which returns thread-specific FlowActions. The handler (Phase 8) will map these actions to Telegram responses.

**Tech Stack:** Python 3.11+, pytest, dataclasses, enum

---

## Background

In Telegram forum groups, each topic has a `message_thread_id`. When `/start` is called in a topic:
1. If no project exists for chat → ask for project name
2. If thread exists with `name="pending"` → upgrade it (assign magic name)
3. If thread exists (not pending) → check tmux, show status or launch
4. If `thread_id` not in `project.threads` → register as unknown topic

## Handler Behavior (Phase 8)

**IMPORTANT:** The Phase 8 handler must launch Claude when receiving these actions:
- `UPGRADE_PENDING_THREAD` → launch Claude in the upgraded thread
- `REGISTER_UNKNOWN_TOPIC` → launch Claude in the newly registered topic
- `THREAD_LAUNCH` → launch Claude in the existing thread

The service only returns *intent*, the handler executes the action.

## New Imports Required

Add these imports to `src/codogram/services/start_flow.py`:
```python
from ..tmux import TmuxSession  # Already have find_all_tmux_by_cwd, find_tmux_by_convention
from ..magic_names import get_random_magic_name
from ..session_manager import ThreadInfo
```

## Task 1: Add thread-related FlowActions

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Test: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestThreadFlowActions:
    """Tests for thread-specific FlowActions."""

    def test_has_thread_show_status(self):
        assert FlowAction.THREAD_SHOW_STATUS.value == "thread_show_status"

    def test_has_thread_launch(self):
        assert FlowAction.THREAD_LAUNCH.value == "thread_launch"

    def test_has_upgrade_pending_thread(self):
        assert FlowAction.UPGRADE_PENDING_THREAD.value == "upgrade_pending_thread"

    def test_has_register_unknown_topic(self):
        assert FlowAction.REGISTER_UNKNOWN_TOPIC.value == "register_unknown_topic"
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestThreadFlowActions -v
```

Expected: FAIL with `AttributeError: THREAD_SHOW_STATUS`

**Step 3: Add FlowActions to enum**

In `src/codogram/services/start_flow.py`, add to `FlowAction` enum:

```python
class FlowAction(Enum):
    # ... existing ...

    # Thread-specific
    THREAD_SHOW_STATUS = "thread_show_status"
    THREAD_LAUNCH = "thread_launch"
    UPGRADE_PENDING_THREAD = "upgrade_pending_thread"
    REGISTER_UNKNOWN_TOPIC = "register_unknown_topic"
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestThreadFlowActions -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add thread-specific FlowActions"
```

---

## Task 2: Add thread fields to FlowResult

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestFlowResultThreadFields:
    """Tests for thread fields in FlowResult."""

    def test_has_thread_id_field(self):
        result = FlowResult(action=FlowAction.THREAD_LAUNCH, thread_id=123)
        assert result.thread_id == 123

    def test_has_thread_name_field(self):
        result = FlowResult(action=FlowAction.THREAD_LAUNCH, thread_name="mystic")
        assert result.thread_name == "mystic"

    def test_thread_fields_default_none(self):
        result = FlowResult(action=FlowAction.LAUNCH)
        assert result.thread_id is None
        assert result.thread_name is None
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestFlowResultThreadFields -v
```

Expected: FAIL with `TypeError: unexpected keyword argument 'thread_id'`

**Step 3: Add fields to FlowResult**

In `src/codogram/services/start_flow.py`, update `FlowResult`:

```python
@dataclass
class FlowResult:
    """Result of a flow step."""

    action: FlowAction
    project: str | None = None
    path: str | None = None
    tmux_session: str | None = None
    tmux_list: list[str] | None = None
    message: str | None = None
    error: str | None = None
    # Thread-specific
    thread_id: int | None = None
    thread_name: str | None = None
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestFlowResultThreadFields -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add thread_id and thread_name to FlowResult"
```

---

## Task 3: Add thread_id parameter to handle_start

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleStartWithThreadId:
    """Tests for handle_start with thread_id parameter."""

    def test_thread_id_none_uses_existing_flow(self):
        """thread_id=None should use existing non-topic flow."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_start(chat_id=123, args=[], thread_id=None)

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_thread_id_provided_no_project(self):
        """thread_id provided but no project -> ASK_PROJECT_NAME."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm, Mock())
        result = service.handle_start(chat_id=123, args=[], thread_id=456)

        assert result.action == FlowAction.ASK_PROJECT_NAME
        assert result.thread_id == 456
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleStartWithThreadId -v
```

Expected: FAIL with `TypeError: handle_start() got an unexpected keyword argument 'thread_id'`

**Step 3: Add thread_id parameter**

In `src/codogram/services/start_flow.py`, update `handle_start`:

```python
def handle_start(
    self,
    chat_id: int,
    args: list[str],
    chat_title: str | None = None,
    thread_id: int | None = None,  # NEW
) -> FlowResult:
    """Entry point for /start command.

    Args:
        chat_id: Telegram chat ID
        args: Command arguments (e.g., ["project-name"])
        chat_title: Chat title for auto-naming
        thread_id: Topic thread ID (None for main chat)

    Returns:
        FlowResult with next action to take
    """
    # Topic mode
    if thread_id is not None:
        return self._handle_topic_start(chat_id, thread_id, args)

    # ... rest of existing logic unchanged
```

Add placeholder method:

```python
def _handle_topic_start(
    self, chat_id: int, thread_id: int, args: list[str]
) -> FlowResult:
    """Handle /start in a topic."""
    # Case 1: No project for this chat
    project = self.pm.get_by_chat(chat_id)
    if not project:
        return FlowResult(
            action=FlowAction.ASK_PROJECT_NAME,
            thread_id=thread_id,
        )

    # TODO: More cases in next tasks
    return FlowResult(action=FlowAction.ERROR, error="Not implemented")
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleStartWithThreadId -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): add thread_id parameter to handle_start"
```

---

## Task 4: Handle existing thread (not pending)

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleTopicExistingThread:
    """Tests for topic start with existing thread."""

    def test_thread_exists_tmux_running(self):
        """Thread exists, tmux running -> THREAD_SHOW_STATUS."""
        mock_pm = Mock()
        thread = Mock()
        thread.thread_id = 456
        thread.name = "mystic"
        thread.get_tmux_session.return_value = "claude-test-mystic"
        project = Mock(
            project_name="test",
            cwd="/tmp/test",
            threads={456: thread},
        )
        mock_pm.get_by_chat.return_value = project

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.TmuxSession") as mock_tmux:
            mock_tmux.return_value.exists.return_value = True
            result = service.handle_start(chat_id=123, args=[], thread_id=456)

        assert result.action == FlowAction.THREAD_SHOW_STATUS
        assert result.thread_id == 456
        assert result.tmux_session == "claude-test-mystic"

    def test_thread_exists_no_tmux(self):
        """Thread exists, no tmux -> THREAD_LAUNCH."""
        mock_pm = Mock()
        thread = Mock()
        thread.thread_id = 456
        thread.name = "mystic"
        thread.get_tmux_session.return_value = "claude-test-mystic"
        project = Mock(
            project_name="test",
            cwd="/tmp/test",
            threads={456: thread},
        )
        mock_pm.get_by_chat.return_value = project

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.TmuxSession") as mock_tmux:
            mock_tmux.return_value.exists.return_value = False
            result = service.handle_start(chat_id=123, args=[], thread_id=456)

        assert result.action == FlowAction.THREAD_LAUNCH
        assert result.thread_id == 456
        assert result.thread_name == "mystic"
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleTopicExistingThread -v
```

**Step 3: Implement existing thread handling**

Add import at top of `src/codogram/services/start_flow.py`:

```python
from ..tmux import find_all_tmux_by_cwd, find_tmux_by_convention, TmuxSession
```

Update `_handle_topic_start`:

```python
def _handle_topic_start(
    self, chat_id: int, thread_id: int, args: list[str]
) -> FlowResult:
    """Handle /start in a topic."""
    # Case 1: No project for this chat
    project = self.pm.get_by_chat(chat_id)
    if not project:
        return FlowResult(
            action=FlowAction.ASK_PROJECT_NAME,
            thread_id=thread_id,
        )

    # Case 2: Thread exists
    thread = project.threads.get(thread_id)
    if thread:
        if thread.name == "pending":
            # TODO: Task 5
            pass
        else:
            return self._check_thread_tmux(project, thread)

    # TODO: Case 3 in Task 6
    return FlowResult(action=FlowAction.ERROR, error="Not implemented")

def _check_thread_tmux(self, project, thread) -> FlowResult:
    """Check tmux for thread and return appropriate action."""
    tmux_name = thread.get_tmux_session(project.project_name)
    tmux = TmuxSession(tmux_name, project.cwd)

    if tmux.exists():
        return FlowResult(
            action=FlowAction.THREAD_SHOW_STATUS,
            project=project.project_name,
            path=project.cwd,
            tmux_session=tmux_name,
            thread_id=thread.thread_id,
            thread_name=thread.name,
        )
    else:
        return FlowResult(
            action=FlowAction.THREAD_LAUNCH,
            project=project.project_name,
            path=project.cwd,
            thread_id=thread.thread_id,
            thread_name=thread.name,
        )
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleTopicExistingThread -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): handle existing thread in topic start"
```

---

## Task 5: Handle pending thread upgrade

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandlePendingThread:
    """Tests for upgrading pending threads."""

    def test_pending_thread_gets_upgraded(self):
        """Pending thread -> UPGRADE_PENDING_THREAD with generated name."""
        mock_pm = Mock()
        pending_thread = Mock()
        pending_thread.thread_id = 456
        pending_thread.name = "pending"
        project = Mock(
            project_name="test",
            cwd="/tmp/test",
            threads={456: pending_thread},
        )
        mock_pm.get_by_chat.return_value = project

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.get_random_magic_name") as mock_name:
            mock_name.return_value = "ethereal"
            result = service.handle_start(chat_id=123, args=[], thread_id=456)

        assert result.action == FlowAction.UPGRADE_PENDING_THREAD
        assert result.thread_id == 456
        assert result.thread_name == "ethereal"
        assert pending_thread.name == "ethereal"
        mock_pm._save.assert_called_once()

    def test_pending_thread_excludes_existing_names(self):
        """Magic name excludes names already in use."""
        mock_pm = Mock()
        pending_thread = Mock()
        pending_thread.thread_id = 456
        pending_thread.name = "pending"
        existing_thread = Mock()
        existing_thread.thread_id = 789
        existing_thread.name = "mystic"
        project = Mock(
            project_name="test",
            cwd="/tmp/test",
            threads={456: pending_thread, 789: existing_thread},
        )
        mock_pm.get_by_chat.return_value = project

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.get_random_magic_name") as mock_name:
            mock_name.return_value = "arcane"
            result = service.handle_start(chat_id=123, args=[], thread_id=456)

        # Verify excluded names were passed
        mock_name.assert_called_once()
        excluded = mock_name.call_args[0][0]
        assert "mystic" in excluded
        assert "pending" not in excluded  # pending is special, not excluded
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandlePendingThread -v
```

**Step 3: Implement pending thread upgrade**

Add import at top of `src/codogram/services/start_flow.py`:

```python
from ..magic_names import get_random_magic_name
```

Update `_handle_topic_start` to handle pending:

```python
def _handle_topic_start(
    self, chat_id: int, thread_id: int, args: list[str]
) -> FlowResult:
    """Handle /start in a topic."""
    # Case 1: No project for this chat
    project = self.pm.get_by_chat(chat_id)
    if not project:
        return FlowResult(
            action=FlowAction.ASK_PROJECT_NAME,
            thread_id=thread_id,
        )

    # Case 2: Thread exists
    thread = project.threads.get(thread_id)
    if thread:
        if thread.name == "pending":
            return self._upgrade_pending_thread(project, thread)
        else:
            return self._check_thread_tmux(project, thread)

    # TODO: Case 3 in Task 6
    return FlowResult(action=FlowAction.ERROR, error="Not implemented")

def _upgrade_pending_thread(self, project, thread) -> FlowResult:
    """Upgrade a pending thread with a magic name."""
    # Get existing names to exclude
    existing_names = {
        t.name for t in project.threads.values()
        if t.name and t.name != "pending"
    }

    # Generate unique name
    new_name = get_random_magic_name(existing_names)
    thread.name = new_name
    self.pm._save()

    return FlowResult(
        action=FlowAction.UPGRADE_PENDING_THREAD,
        project=project.project_name,
        path=project.cwd,
        thread_id=thread.thread_id,
        thread_name=new_name,
    )
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandlePendingThread -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): handle pending thread upgrade with magic names"
```

---

## Task 6: Handle unknown topic registration

**Files:**
- Modify: `src/codogram/services/start_flow.py`
- Modify: `tests/test_start_flow_service.py`

**Step 1: Write the failing tests**

Add to `tests/test_start_flow_service.py`:

```python
class TestHandleUnknownTopic:
    """Tests for registering unknown topics."""

    def test_unknown_topic_gets_registered(self):
        """Unknown thread_id -> REGISTER_UNKNOWN_TOPIC."""
        mock_pm = Mock()
        project = Mock(
            project_name="test",
            cwd="/tmp/test",
            threads={},  # No threads
        )
        mock_pm.get_by_chat.return_value = project

        service = StartFlowService(mock_pm, Mock())

        with patch("codogram.services.start_flow.get_random_magic_name") as mock_name:
            mock_name.return_value = "cosmic"
            result = service.handle_start(chat_id=123, args=[], thread_id=999)

        assert result.action == FlowAction.REGISTER_UNKNOWN_TOPIC
        assert result.thread_id == 999
        assert result.thread_name == "cosmic"
        # Thread should be created
        assert 999 in project.threads
        assert project.threads[999].name == "cosmic"
        mock_pm._save.assert_called_once()
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleUnknownTopic -v
```

**Step 3: Implement unknown topic registration**

Add import at top if not present:

```python
from ..session_manager import ThreadInfo
```

Update `_handle_topic_start`:

```python
def _handle_topic_start(
    self, chat_id: int, thread_id: int, args: list[str]
) -> FlowResult:
    """Handle /start in a topic."""
    # Case 1: No project for this chat
    project = self.pm.get_by_chat(chat_id)
    if not project:
        return FlowResult(
            action=FlowAction.ASK_PROJECT_NAME,
            thread_id=thread_id,
        )

    # Case 2: Thread exists
    thread = project.threads.get(thread_id)
    if thread:
        if thread.name == "pending":
            return self._upgrade_pending_thread(project, thread)
        else:
            return self._check_thread_tmux(project, thread)

    # Case 3: Unknown topic - register it
    return self._register_unknown_topic(project, thread_id)

def _register_unknown_topic(self, project, thread_id: int) -> FlowResult:
    """Register an unknown topic with a new ThreadInfo."""
    # Get existing names to exclude
    existing_names = {
        t.name for t in project.threads.values()
        if t.name and t.name != "pending"
    }

    # Generate unique name
    new_name = get_random_magic_name(existing_names)

    # Create and register thread
    thread = ThreadInfo(thread_id=thread_id, name=new_name)
    project.threads[thread_id] = thread
    self.pm._save()

    return FlowResult(
        action=FlowAction.REGISTER_UNKNOWN_TOPIC,
        project=project.project_name,
        path=project.cwd,
        thread_id=thread_id,
        thread_name=new_name,
    )
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py::TestHandleUnknownTopic -v
```

**Step 5: Commit**

```bash
git add src/codogram/services/start_flow.py tests/test_start_flow_service.py
git commit -m "feat(start_flow): register unknown topics with magic names"
```

---

## Task 7: Final verification and cleanup

**Files:**
- All files from previous tasks

**Step 1: Run all Phase 7b tests**

```bash
PYTHONPATH=src pytest tests/test_start_flow_service.py -v -k "Thread or Topic or Pending"
```

Expected: All thread-related tests PASS

**Step 2: Run full test suite**

```bash
PYTHONPATH=src pytest tests/ -v
```

Expected: All tests PASS (no regressions)

**Step 3: Verify import works**

```bash
PYTHONPATH=src python -c "from codogram.services.start_flow import StartFlowService, FlowAction; print('FlowActions:', [a.name for a in FlowAction if 'THREAD' in a.name or 'TOPIC' in a.name])"
```

Expected: `FlowActions: ['THREAD_SHOW_STATUS', 'THREAD_LAUNCH', 'UPGRADE_PENDING_THREAD', 'REGISTER_UNKNOWN_TOPIC']`

**Step 4: Final commit if needed**

```bash
git status
# If any uncommitted changes:
git add -A
git commit -m "chore: cleanup Phase 7b implementation"
```

---

## Summary

**Files created/modified:**
- `src/codogram/services/start_flow.py` - extended with thread support
- `tests/test_start_flow_service.py` - added thread-related tests

**New FlowActions:**
- `THREAD_SHOW_STATUS` - thread's tmux exists
- `THREAD_LAUNCH` - need to launch Claude in thread
- `UPGRADE_PENDING_THREAD` - pending thread upgraded with magic name
- `REGISTER_UNKNOWN_TOPIC` - new topic registered

**New FlowResult fields:**
- `thread_id: int | None`
- `thread_name: str | None`

**New/updated methods in StartFlowService:**
1. `handle_start()` - added `thread_id` parameter
2. `_handle_topic_start()` - topic-specific flow
3. `_check_thread_tmux()` - check if thread's tmux exists
4. `_upgrade_pending_thread()` - upgrade pending → magic name
5. `_register_unknown_topic()` - create ThreadInfo for unknown topic

**Next steps:**
- Phase 7c: Restart flow
- Phase 8: Create handlers/start.py that uses StartFlowService
