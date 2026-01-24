"""Tests for StartFlowService."""
import os
from unittest.mock import Mock, patch

import pytest

# Set env before imports
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("BASE_DIR", "/tmp")

from codogram.services.start_flow import FlowAction, FlowResult, StartFlowService


class TestFlowAction:
    def test_has_ask_project_name(self):
        assert FlowAction.ASK_PROJECT_NAME.value == "ask_project_name"

    def test_has_error(self):
        assert FlowAction.ERROR.value == "error"

    def test_has_launch(self):
        assert FlowAction.LAUNCH.value == "launch"

    def test_ask_clone_url_retry_action_exists(self):
        assert hasattr(FlowAction, 'ASK_CLONE_URL_RETRY')
        assert FlowAction.ASK_CLONE_URL_RETRY.value == "ask_clone_url_retry"


class TestFlowResult:
    def test_default_values(self):
        result = FlowResult(action=FlowAction.ERROR)
        assert result.action == FlowAction.ERROR
        assert result.project is None
        assert result.path is None
        assert result.error is None

    def test_with_all_fields(self):
        result = FlowResult(
            action=FlowAction.ASK_DIR_CHOICE,
            project="my-project",
            path="/tmp/my-project",
            error="Some error",
        )
        assert result.project == "my-project"
        assert result.path == "/tmp/my-project"
        assert result.error == "Some error"


class TestHandleStartWithProjectName:
    """Tests for handle_start when project name is provided in args."""

    def test_valid_project_name_no_existing_dir(self):
        """Valid project name, directory doesn't exist -> ASK_DIR_CHOICE."""
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/my-project", exists=False)
            result = service.handle_start(chat_id=123, args=["my-project"])

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "my-project"
        assert result.path == "/tmp/my-project"

    def test_invalid_project_name_with_space(self):
        """Project name with space -> ERROR."""
        service = StartFlowService(Mock())

        result = service.handle_start(chat_id=123, args=["my project"])

        assert result.action == FlowAction.ERROR
        assert "letters, digits" in result.error.lower() or "only contain" in result.error.lower()

    def test_project_name_too_long(self):
        """Project name > 50 chars -> ERROR."""
        service = StartFlowService(Mock())

        result = service.handle_start(chat_id=123, args=["a" * 55])

        assert result.action == FlowAction.ERROR
        assert "too long" in result.error.lower()


class TestHandleStartNoArgs:
    """Tests for handle_start when no args provided."""

    def test_no_project_no_title_asks_name(self):
        """No project, no chat title -> ASK_PROJECT_NAME."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm)
        result = service.handle_start(chat_id=123, args=[], chat_title=None)

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_uses_chat_title_if_valid(self):
        """No project, valid chat title -> start flow with sanitized title."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/my-project", exists=False)
            result = service.handle_start(
                chat_id=123, args=[], chat_title="My Project!"
            )

        assert result.action == FlowAction.ASK_DIR_CHOICE
        # sanitize_project_name now lowercases the result
        assert result.project == "my-project"

    def test_ignores_invalid_chat_title(self):
        """Chat title that sanitizes to empty -> ASK_PROJECT_NAME."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm)
        result = service.handle_start(chat_id=123, args=[], chat_title="!!!")

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_existing_project_not_running(self):
        """Existing project for chat, not running -> start flow."""
        mock_pm = Mock()
        existing = Mock(
            project_name="existing-project",
            cwd=None,
            chat_id=123,
            tmux_session=None,
            threads=Mock(get=Mock(return_value=None)),  # No configured thread
        )
        mock_pm.get_by_chat.return_value = existing
        mock_pm.get_or_create.return_value = existing

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(
                path="/tmp/existing-project", exists=False
            )
            result = service.handle_start(chat_id=123, args=[])

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "existing-project"


class TestConnectOrLaunch:
    """Tests for _connect_or_launch method."""

    def test_no_tmux_found_asks_launch(self):
        """No tmux sessions in cwd -> ASK_LAUNCH_CONFIRM."""
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp/test", tmux_session=None)

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.find_all_tmux_by_cwd", return_value=[]
        ):
            with patch(
                "codogram.services.start.flow.find_tmux_by_convention",
                return_value=None,
            ):
                result = service._connect_or_launch(project)

        assert result.action == FlowAction.ASK_LAUNCH_CONFIRM
        assert result.project == "test"
        assert result.path == "/tmp/test"

    def test_one_tmux_found_connects(self):
        """One tmux session in cwd -> CONNECT."""
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp/test", tmux_session=None)

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.find_all_tmux_by_cwd",
            return_value=["claude-test"],
        ):
            result = service._connect_or_launch(project)

        assert result.action == FlowAction.CONNECT
        assert result.tmux_session == "claude-test"
        assert project.tmux_session == "claude-test"

    def test_multiple_tmux_found_selects(self):
        """Multiple tmux sessions -> SELECT_TMUX."""
        mock_pm = Mock()
        project = Mock(project_name="test", cwd="/tmp/test", tmux_session=None)

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.find_all_tmux_by_cwd",
            return_value=["session1", "session2"],
        ):
            result = service._connect_or_launch(project)

        assert result.action == FlowAction.ASK_TMUX_SELECT
        assert result.tmux_list == ["session1", "session2"]

    def test_finds_by_convention(self):
        """No tmux in cwd, but found by convention -> CONNECT."""
        mock_pm = Mock()
        project = Mock(project_name="myproj", cwd="/tmp/myproj", tmux_session=None)

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.find_all_tmux_by_cwd", return_value=[]
        ):
            with patch(
                "codogram.services.start.flow.find_tmux_by_convention",
                return_value="claude-myproj",
            ):
                result = service._connect_or_launch(project)

        assert result.action == FlowAction.CONNECT
        assert result.tmux_session == "claude-myproj"


class TestShowStatus:
    """Tests for showing status of running project."""

    def test_running_project_shows_status(self):
        """Running project -> SHOW_STATUS."""
        mock_pm = Mock()
        running = Mock(
            project_name="running",
            cwd="/tmp/running",
            tmux_session="claude-running",
            poller_task=Mock(done=Mock(return_value=False)),
            watcher_task=Mock(done=Mock(return_value=False)),
            threads=Mock(get=Mock(return_value=None)),  # No configured thread
        )
        mock_pm.get_by_chat.return_value = running

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.is_tmux_session_exists", return_value=True
        ):
            result = service.handle_start(chat_id=123, args=[])

        assert result.action == FlowAction.SHOW_STATUS
        assert result.project == "running"
        assert result.tmux_session == "claude-running"


class TestHandleProjectName:
    """Tests for handle_project_name (FSM state handler)."""

    def test_valid_name_starts_flow(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/test", exists=False)
            result = service.handle_project_name(chat_id=123, name="my-project")

        assert result.action == FlowAction.ASK_DIR_CHOICE
        assert result.project == "my-project"

    def test_invalid_name_returns_error(self):
        service = StartFlowService(Mock())
        result = service.handle_project_name(chat_id=123, name="invalid name")

        assert result.action == FlowAction.ERROR

    def test_strips_whitespace(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)

        with patch(
            "codogram.services.start.flow.resolve_project_path"
        ) as mock_resolve:
            mock_resolve.return_value = Mock(path="/tmp/test", exists=False)
            result = service.handle_project_name(chat_id=123, name="  my-project  ")

        assert result.project == "my-project"


class TestHandleCreateDir:
    """Tests for handle_create_dir (Create directory button)."""

    def test_creates_dir_and_asks_git(self, tmp_path):
        service = StartFlowService(Mock())
        new_dir = tmp_path / "new_project"

        result = service.handle_create_dir(project="test", path=str(new_dir))

        assert result.action == FlowAction.ASK_GIT_CHOICE
        assert result.project == "test"
        assert new_dir.exists()

    def test_works_with_existing_dir(self, tmp_path):
        service = StartFlowService(Mock())
        existing = tmp_path / "existing"
        existing.mkdir()

        result = service.handle_create_dir(project="test", path=str(existing))

        assert result.action == FlowAction.ASK_GIT_CHOICE


class TestHandleCustomPath:
    """Tests for handle_custom_path (Custom path input)."""

    def test_valid_path_launches(self, tmp_path):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)
        result = service.handle_custom_path(
            chat_id=123, project="test", path=str(tmp_path)
        )

        assert result.action == FlowAction.LAUNCH
        assert result.project == "test"
        assert result.path == str(tmp_path)

    def test_nonexistent_path_returns_error(self):
        service = StartFlowService(Mock())
        result = service.handle_custom_path(
            chat_id=123, project="test", path="/nonexistent/path"
        )

        assert result.action == FlowAction.ERROR
        assert "not exist" in result.error.lower() or "does not exist" in result.error.lower()

    def test_expands_tilde(self, tmp_path, monkeypatch):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        # Mock os.path.expanduser to expand ~ to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        service = StartFlowService(mock_pm)
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = service.handle_custom_path(
            chat_id=123, project="test", path="~/test"
        )

        assert result.action == FlowAction.LAUNCH


class TestGitMethods:
    """Tests for git-related methods."""

    def test_handle_git_init_launches(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.git_init") as mock_git:
            mock_git.return_value = Mock(success=True)
            result = service.handle_git_init(
                chat_id=123, project="test", path="/tmp/test"
            )

        assert result.action == FlowAction.LAUNCH
        mock_git.assert_called_once_with("/tmp/test")

    def test_handle_no_git_launches(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)
        result = service.handle_no_git(
            chat_id=123, project="test", path="/tmp/test"
        )

        assert result.action == FlowAction.LAUNCH
        assert result.project == "test"

    def test_handle_gh_create_private(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.git_init_with_github") as mock_gh:
            mock_gh.return_value = Mock(success=True)
            result = service.handle_gh_create(
                chat_id=123, project="test", path="/tmp/test", private=True
            )

        assert result.action == FlowAction.LAUNCH
        mock_gh.assert_called_once_with("/tmp/test", private=True)

    def test_handle_gh_create_error(self):
        mock_pm = Mock()
        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.git_init_with_github") as mock_gh:
            mock_gh.return_value = Mock(success=False, error="gh auth required")
            result = service.handle_gh_create(
                chat_id=123, project="test", path="/tmp/test", private=False
            )

        assert result.action == FlowAction.ERROR
        assert "gh auth" in result.error.lower() or "failed" in result.error.lower()


class TestHandleCloneUrl:
    """Tests for handle_clone_url."""

    def test_validates_wiki_url(self):
        """Wiki URL -> ASK_CLONE_URL_RETRY with wiki error."""
        pm = Mock()
        service = StartFlowService(pm)

        result = service.handle_clone_url(
            chat_id=123,
            project="test",
            path="/tmp/test",
            url="https://github.com/user/repo/wiki/Page",
        )

        assert result.action == FlowAction.ASK_CLONE_URL_RETRY
        assert "wiki" in result.error.lower()

    def test_validates_blob_url(self):
        """Blob URL -> ASK_CLONE_URL_RETRY with file error."""
        pm = Mock()
        service = StartFlowService(pm)

        result = service.handle_clone_url(
            chat_id=123,
            project="test",
            path="/tmp/test",
            url="https://github.com/user/repo/blob/main/file.py",
        )

        assert result.action == FlowAction.ASK_CLONE_URL_RETRY
        assert "file" in result.error.lower()

    def test_valid_https_url(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.git_clone") as mock_clone:
            mock_clone.return_value = Mock(success=True)
            result = service.handle_clone_url(
                chat_id=123,
                project="test",
                path="/tmp/test",
                url="https://github.com/user/repo.git",
            )

        assert result.action == FlowAction.LAUNCH
        mock_clone.assert_called_once()

    def test_valid_ssh_url(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.git_clone") as mock_clone:
            mock_clone.return_value = Mock(success=True)
            result = service.handle_clone_url(
                chat_id=123,
                project="test",
                path="/tmp/test",
                url="git@github.com:user/repo.git",
            )

        assert result.action == FlowAction.LAUNCH

    def test_invalid_url_format(self):
        """Invalid URL format -> ASK_CLONE_URL_RETRY to allow correction."""
        service = StartFlowService(Mock())
        result = service.handle_clone_url(
            chat_id=123,
            project="test",
            path="/tmp/test",
            url="not-a-valid-url",
        )

        assert result.action == FlowAction.ASK_CLONE_URL_RETRY
        assert "invalid" in result.error.lower() or "url" in result.error.lower()

    def test_clone_failure(self):
        """Clone failure -> ASK_CLONE_URL_RETRY to allow URL correction."""
        service = StartFlowService(Mock())

        with patch("codogram.services.start.flow.git_clone") as mock_clone:
            mock_clone.return_value = Mock(success=False, error="repo not found")
            result = service.handle_clone_url(
                chat_id=123,
                project="test",
                path="/tmp/test",
                url="https://github.com/user/repo.git",
            )

        assert result.action == FlowAction.ASK_CLONE_URL_RETRY
        assert "clone failed" in result.error.lower()


class TestHandleTmuxSelected:
    """Tests for handle_tmux_selected."""

    def test_selects_tmux_and_connects(self):
        mock_pm = Mock()
        mock_pm.get_or_create.return_value = Mock(cwd=None, chat_id=None)

        service = StartFlowService(mock_pm)
        result = service.handle_tmux_selected(
            chat_id=123,
            project_name="test",
            tmux_session="session-1",
        )

        assert result.action == FlowAction.CONNECT
        assert result.tmux_session == "session-1"
        mock_pm._save.assert_called_once()


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


class TestHandleStartWithThreadId:
    """Tests for handle_start with thread_id parameter."""

    def test_thread_id_none_uses_existing_flow(self):
        """thread_id=None should use existing non-topic flow."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm)
        result = service.handle_start(chat_id=123, args=[], thread_id=None)

        assert result.action == FlowAction.ASK_PROJECT_NAME

    def test_thread_id_provided_no_project(self):
        """thread_id provided but no project -> ASK_PROJECT_NAME."""
        mock_pm = Mock()
        mock_pm.get_by_chat.return_value = None

        service = StartFlowService(mock_pm)
        result = service.handle_start(chat_id=123, args=[], thread_id=456)

        assert result.action == FlowAction.ASK_PROJECT_NAME
        assert result.thread_id == 456


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

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.TmuxSession") as mock_tmux:
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

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.TmuxSession") as mock_tmux:
            mock_tmux.return_value.exists.return_value = False
            result = service.handle_start(chat_id=123, args=[], thread_id=456)

        assert result.action == FlowAction.THREAD_LAUNCH
        assert result.thread_id == 456
        assert result.thread_name == "mystic"


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

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.get_random_magic_name") as mock_name:
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

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.get_random_magic_name") as mock_name:
            mock_name.return_value = "arcane"
            result = service.handle_start(chat_id=123, args=[], thread_id=456)

        # Verify excluded names were passed
        mock_name.assert_called_once()
        excluded = mock_name.call_args[0][0]
        assert "mystic" in excluded
        assert "pending" not in excluded  # pending is special, not excluded


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

        service = StartFlowService(mock_pm)

        with patch("codogram.services.start.flow.get_random_magic_name") as mock_name:
            mock_name.return_value = "cosmic"
            result = service.handle_start(chat_id=123, args=[], thread_id=999)

        assert result.action == FlowAction.REGISTER_UNKNOWN_TOPIC
        assert result.thread_id == 999
        assert result.thread_name == "cosmic"
        # Thread should be created
        assert 999 in project.threads
        assert project.threads[999].name == "cosmic"
        mock_pm._save.assert_called_once()


class TestIsSetupPhase:
    """Tests for is_setup_phase() function."""

    def test_is_setup_phase_no_threads(self):
        """No threads at all -> True."""
        from codogram.services.start_flow import is_setup_phase
        from codogram.core.session_manager import ProjectState

        project = ProjectState(project_name="test")
        assert is_setup_phase(project) is True

    def test_is_setup_phase_main_thread_no_session(self):
        """Main thread exists but no session_id -> True."""
        from codogram.services.start_flow import is_setup_phase
        from codogram.core.session_manager import ProjectState, ThreadInfo

        project = ProjectState(project_name="test")
        project.threads[None] = ThreadInfo(thread_id=None, name="main")
        assert is_setup_phase(project) is True

    def test_is_setup_phase_main_thread_with_session(self):
        """Main thread has session_id -> False."""
        from codogram.services.start_flow import is_setup_phase
        from codogram.core.session_manager import ProjectState, ThreadInfo

        project = ProjectState(project_name="test")
        project.threads[None] = ThreadInfo(thread_id=None, name="main", session_id="abc123")
        assert is_setup_phase(project) is False

    def test_is_setup_phase_legacy_session_id(self):
        """Legacy projects have session_id on project, not thread."""
        from codogram.services.start_flow import is_setup_phase
        from codogram.core.session_manager import ProjectState

        project = ProjectState(project_name="test")
        project.session_id = "legacy-session"
        assert is_setup_phase(project) is False


class TestBuildAnnouncement:
    """Tests for build_announcement() helper."""

    def test_build_announcement_non_forum(self):
        from codogram.services.start_flow import build_announcement

        result = build_announcement("test-project", "claude-test", is_forum=False)

        assert "test-project" in result
        assert "claude-test" in result
        assert "/esc" in result
        assert "/clear" in result
        assert "/auto_accept" in result
        assert "/new_chat" not in result  # Forum-only
        assert "/finish_chat" not in result

    def test_build_announcement_forum(self):
        from codogram.services.start_flow import build_announcement

        result = build_announcement("test-project", "claude-test", is_forum=True)

        assert "/new_chat" in result
        assert "/finish_chat" in result