# DM Onboarding + Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add DM onboarding flow for new admins and /dash command to view all projects.

**Architecture:** New `handlers/dm.py` for DM-specific commands, `services/dm_onboarding.py` for business logic, `services/dashboard.py` for dashboard data, `keyboards/dm_onboarding.py` for buttons. Extends config.json with `users` section for onboarding state.

**Tech Stack:** aiogram 3.x, existing config.py patterns, shutil.which for binary checks.

---

## Task 1: Extend Config for User Storage

**Files:**
- Modify: `src/codogram/config.py`
- Test: `tests/test_config_users.py`

**Step 1: Write the failing test**

```python
# tests/test_config_users.py
"""Tests for user storage in config."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_load_config_returns_users_key():
    """Config should always have users key."""
    from codogram.config import load_config

    with patch("codogram.config.CONFIG_PATH") as mock_path:
        mock_path.exists.return_value = False
        config = load_config()

    assert "users" in config
    assert "projects" in config


def test_get_user_onboarded_false_for_new_user():
    """New users should not be onboarded."""
    from codogram.config import get_user_onboarded

    with patch("codogram.config.load_config") as mock_load:
        mock_load.return_value = {"users": {}, "projects": {}}
        result = get_user_onboarded(123456)

    assert result is False


def test_get_user_onboarded_true_for_existing_user():
    """Existing onboarded users should return True."""
    from codogram.config import get_user_onboarded

    with patch("codogram.config.load_config") as mock_load:
        mock_load.return_value = {
            "users": {"123456": {"onboarded": True}},
            "projects": {}
        }
        result = get_user_onboarded(123456)

    assert result is True


def test_set_user_onboarded():
    """Should save onboarded state for user."""
    from codogram.config import set_user_onboarded

    saved_config = None
    def capture_save(config):
        nonlocal saved_config
        saved_config = config

    with patch("codogram.config.load_config") as mock_load, \
         patch("codogram.config.save_config", side_effect=capture_save):
        mock_load.return_value = {"users": {}, "projects": {}}
        set_user_onboarded(123456)

    assert saved_config is not None
    assert "123456" in saved_config["users"]
    assert saved_config["users"]["123456"]["onboarded"] is True
    assert "onboarded_at" in saved_config["users"]["123456"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_users.py -v`
Expected: FAIL with ImportError or AttributeError

**Step 3: Write minimal implementation**

Add to `src/codogram/config.py`:

```python
from datetime import datetime

def load_config() -> dict:
    """Load config.json or return default."""
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text())
        # Ensure users key exists for backward compatibility
        if "users" not in config:
            config["users"] = {}
        return config
    return {"projects": {}, "users": {}}


def get_user_onboarded(user_id: int) -> bool:
    """Check if user has completed onboarding."""
    config = load_config()
    user_data = config.get("users", {}).get(str(user_id), {})
    return user_data.get("onboarded", False)


def set_user_onboarded(user_id: int) -> None:
    """Mark user as onboarded."""
    config = load_config()
    if "users" not in config:
        config["users"] = {}
    config["users"][str(user_id)] = {
        "onboarded": True,
        "onboarded_at": datetime.now().isoformat()
    }
    save_config(config)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_users.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/config.py tests/test_config_users.py
git commit -m "feat(config): add user storage for onboarding state"
```

---

## Task 2: Validation Service

**Files:**
- Create: `src/codogram/services/dm_onboarding/__init__.py`
- Create: `src/codogram/services/dm_onboarding/validation.py`
- Test: `tests/services/test_dm_validation.py`

**Step 1: Write the failing test**

```python
# tests/services/test_dm_validation.py
"""Tests for DM onboarding validation service."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_check_base_dir_configured_returns_error_when_empty():
    """Should return error when BASE_DIR is empty."""
    from codogram.services.dm_onboarding.validation import check_base_dir_configured

    with patch("codogram.services.dm_onboarding.validation.settings") as mock_settings:
        mock_settings.base_dir = ""
        result = check_base_dir_configured()

    assert result.ok is False
    assert "BASE_DIR" in result.message


def test_check_base_dir_configured_returns_ok():
    """Should return ok when BASE_DIR is set."""
    from codogram.services.dm_onboarding.validation import check_base_dir_configured

    with patch("codogram.services.dm_onboarding.validation.settings") as mock_settings:
        mock_settings.base_dir = "/home/user/dev"
        result = check_base_dir_configured()

    assert result.ok is True


def test_check_base_dir_exists_returns_error_when_missing():
    """Should return error when BASE_DIR path doesn't exist."""
    from codogram.services.dm_onboarding.validation import check_base_dir_exists

    with patch("codogram.services.dm_onboarding.validation.settings") as mock_settings, \
         patch("codogram.services.dm_onboarding.validation.Path") as mock_path:
        mock_settings.base_dir = "/nonexistent/path"
        mock_path.return_value.exists.return_value = False
        result = check_base_dir_exists()

    assert result.ok is False


def test_check_binary_available_returns_ok_when_found():
    """Should return ok when binary is in PATH."""
    from codogram.services.dm_onboarding.validation import check_binary_available

    with patch("shutil.which", return_value="/usr/bin/claude"):
        result = check_binary_available("claude")

    assert result.ok is True


def test_check_binary_available_returns_error_when_missing():
    """Should return error when binary is not in PATH."""
    from codogram.services.dm_onboarding.validation import check_binary_available

    with patch("shutil.which", return_value=None):
        result = check_binary_available("claude")

    assert result.ok is False
    assert "claude" in result.message


def test_run_critical_checks_returns_all_errors():
    """Should return all critical check results."""
    from codogram.services.dm_onboarding.validation import run_critical_checks

    with patch("codogram.services.dm_onboarding.validation.settings") as mock_settings, \
         patch("codogram.services.dm_onboarding.validation.Path") as mock_path, \
         patch("shutil.which", return_value="/usr/bin/test"):
        mock_settings.base_dir = "/home/user/dev"
        mock_path.return_value.exists.return_value = True

        results = run_critical_checks()

    assert len(results) == 4  # base_dir configured, exists, claude, tmux
    assert all(r.ok for r in results)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_dm_validation.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create package init**

```python
# src/codogram/services/dm_onboarding/__init__.py
"""DM onboarding services."""
from .validation import (
    ValidationResult,
    check_base_dir_configured,
    check_base_dir_exists,
    check_binary_available,
    run_critical_checks,
    run_warning_checks,
)

__all__ = [
    "ValidationResult",
    "check_base_dir_configured",
    "check_base_dir_exists",
    "check_binary_available",
    "run_critical_checks",
    "run_warning_checks",
]
```

**Step 4: Write validation implementation**

```python
# src/codogram/services/dm_onboarding/validation.py
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
    """Run all critical validation checks.

    Returns list of results. If any has ok=False, onboarding should block.
    """
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
    """Run all warning validation checks.

    Returns list of results. These don't block but show warnings.
    """
    return [
        check_git_configured(),
        check_gh_auth(),
        check_ssh_keys(),
    ]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/services/test_dm_validation.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/services/dm_onboarding/ tests/services/test_dm_validation.py
git commit -m "feat(dm): add validation service for environment checks"
```

---

## Task 3: Onboarding Strings

**Files:**
- Modify: `src/codogram/strings.py`

**Step 1: Add DM onboarding strings**

Add to `src/codogram/strings.py`:

```python
# --- DM Onboarding ---

DM_WELCOME = """👋 Привет!

Я Codogram — бот для управления Claude Code через Telegram."""

DM_SLIDE_1 = """📱 *Мобильность*

Запускай задачи с телефона, работай откуда угодно.

Claude работает на сервере — тебе нужен только Telegram."""

DM_SLIDE_2 = """⏰ *Асинхронность*

Запустил задачу → занялся своим → получил уведомление.

Не нужно сидеть и смотреть в терминал."""

DM_SLIDE_3 = """👥 *Команда*

Настрой один раз — работай с коллегами.

Каждый видит что делает Claude, может подтвердить действие."""

DM_VALIDATION_CHECKING = f"{STATUS_PENDING} Проверяю окружение..."

DM_VALIDATION_OK = f"""{STATUS_OK} Окружение готово

Теперь создай группу в Telegram и добавь меня админом.

Я автоматически подхвачу её."""

DM_VALIDATION_ERROR = f"""{STATUS_ERR} Есть проблемы с окружением

{{errors}}

Исправь и нажми «Проверить снова»."""

DM_VALIDATION_WARNINGS = f"""{STATUS_WARN} Предупреждения (не критично):

{{warnings}}"""

DM_CTA = """✅ *Финальный шаг*

Создай группу в Telegram и добавь @{bot_username} админом.

Бот автоматически подхватит её — /start в группе не нужен."""

DM_MINI_STATUS = """👋 С возвращением!

Активных проектов: {projects}
Сессий Claude: {sessions}

/dash — подробный список проектов
/intro — посмотреть введение ещё раз"""

DM_BOT_ADDED = """Меня добавили в «{chat_name}»
Создатель: @{creator}"""

DM_BOT_ADDED_WITH_LINK = """Меня добавили в «{chat_name}»
Чат: {link}
Создатель: @{creator}"""

# --- Dashboard ---

DASH_HEADER = "📊 Проекты"

DASH_PROJECT = """{num}. {chat_name}
   📁 {directory}
   👤 Создатель: @{creator}
   👥 {members} участник(ов)
   {status}"""

DASH_STATUS_ACTIVE = "🤖 {count} сессий Claude"
DASH_STATUS_INACTIVE = "💤 не активен"

DASH_FOOTER = "Всего: {total} проектов, {active} активных сессий"

DASH_EMPTY = """📊 Проекты

Пока нет подключённых проектов.

Создай группу и добавь меня — я подхвачу автоматически."""

# --- DM Buttons ---

BTN_NEXT = "Далее →"
BTN_PREV = "← Назад"
BTN_RECHECK = "Проверить снова"
BTN_REFRESH = "Обновить"
```

**Step 2: Commit**

```bash
git add src/codogram/strings.py
git commit -m "feat(strings): add DM onboarding and dashboard strings"
```

---

## Task 4: Carousel and Dashboard Keyboards

**Files:**
- Create: `src/codogram/keyboards/dm_onboarding.py`
- Test: `tests/keyboards/test_dm_onboarding.py`

**Step 1: Write the failing test**

```python
# tests/keyboards/test_dm_onboarding.py
"""Tests for DM onboarding keyboards."""
import pytest


def test_carousel_keyboard_first_slide():
    """First slide should only have Next button."""
    from codogram.keyboards.dm_onboarding import carousel_keyboard

    kb = carousel_keyboard(current_slide=0, total_slides=3)
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 1
    assert buttons[0].text == "Далее →"
    assert buttons[0].callback_data == "onb:slide:1"


def test_carousel_keyboard_middle_slide():
    """Middle slides should have both Prev and Next buttons."""
    from codogram.keyboards.dm_onboarding import carousel_keyboard

    kb = carousel_keyboard(current_slide=1, total_slides=3)
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 2
    assert buttons[0].text == "← Назад"
    assert buttons[0].callback_data == "onb:slide:0"
    assert buttons[1].text == "Далее →"
    assert buttons[1].callback_data == "onb:slide:2"


def test_carousel_keyboard_last_slide():
    """Last slide should only have Prev button."""
    from codogram.keyboards.dm_onboarding import carousel_keyboard

    kb = carousel_keyboard(current_slide=2, total_slides=3)
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 1
    assert buttons[0].text == "← Назад"
    assert buttons[0].callback_data == "onb:slide:1"


def test_validation_recheck_keyboard():
    """Should have recheck button."""
    from codogram.keyboards.dm_onboarding import validation_recheck_keyboard

    kb = validation_recheck_keyboard()
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 1
    assert buttons[0].callback_data == "onb:recheck"


def test_dashboard_keyboard():
    """Should have refresh button."""
    from codogram.keyboards.dm_onboarding import dashboard_keyboard

    kb = dashboard_keyboard()
    buttons = kb.inline_keyboard[0]

    assert len(buttons) == 1
    assert buttons[0].callback_data == "dash:refresh"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/keyboards/test_dm_onboarding.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/codogram/keyboards/dm_onboarding.py
"""Keyboards for DM onboarding and dashboard."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import strings


def carousel_keyboard(current_slide: int, total_slides: int) -> InlineKeyboardMarkup:
    """Build carousel navigation keyboard.

    Args:
        current_slide: 0-indexed current slide number
        total_slides: Total number of slides

    Returns:
        Keyboard with Prev/Next buttons based on position
    """
    buttons = []

    if current_slide > 0:
        buttons.append(InlineKeyboardButton(
            text=strings.BTN_PREV,
            callback_data=f"onb:slide:{current_slide - 1}"
        ))

    if current_slide < total_slides - 1:
        buttons.append(InlineKeyboardButton(
            text=strings.BTN_NEXT,
            callback_data=f"onb:slide:{current_slide + 1}"
        ))

    return InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])


def validation_recheck_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard with recheck button for failed validation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.BTN_RECHECK,
            callback_data="onb:recheck"
        )]
    ])


def dashboard_keyboard() -> InlineKeyboardMarkup:
    """Build dashboard keyboard with refresh button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=strings.BTN_REFRESH,
            callback_data="dash:refresh"
        )]
    ])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/keyboards/test_dm_onboarding.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/keyboards/dm_onboarding.py tests/keyboards/test_dm_onboarding.py
git commit -m "feat(keyboards): add carousel and dashboard keyboards"
```

---

## Task 5: Onboarding Service

**Files:**
- Create: `src/codogram/services/dm_onboarding/onboarding.py`
- Modify: `src/codogram/services/dm_onboarding/__init__.py`
- Test: `tests/services/test_dm_onboarding.py`

**Step 1: Write the failing test**

```python
# tests/services/test_dm_onboarding.py
"""Tests for DM onboarding service."""
import pytest
from unittest.mock import patch


def test_get_slide_content_returns_slides():
    """Should return slide content for valid index."""
    from codogram.services.dm_onboarding import get_slide_content

    slide0 = get_slide_content(0)
    slide1 = get_slide_content(1)
    slide2 = get_slide_content(2)

    assert "Мобильность" in slide0
    assert "Асинхронность" in slide1
    assert "Команда" in slide2


def test_get_slide_content_returns_none_for_invalid():
    """Should return None for invalid slide index."""
    from codogram.services.dm_onboarding import get_slide_content

    assert get_slide_content(-1) is None
    assert get_slide_content(99) is None


def test_get_total_slides():
    """Should return correct number of slides."""
    from codogram.services.dm_onboarding import get_total_slides

    assert get_total_slides() == 3


def test_format_validation_errors():
    """Should format validation errors with fix hints."""
    from codogram.services.dm_onboarding import format_validation_errors
    from codogram.services.dm_onboarding.validation import ValidationResult

    results = [
        ValidationResult(ok=False, name="test1", message="Error 1", fix_hint="Fix 1"),
        ValidationResult(ok=False, name="test2", message="Error 2", fix_hint=""),
    ]

    formatted = format_validation_errors(results)

    assert "Error 1" in formatted
    assert "Fix 1" in formatted
    assert "Error 2" in formatted
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_dm_onboarding.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/codogram/services/dm_onboarding/onboarding.py
"""DM onboarding business logic."""
from .. import strings


SLIDES = [
    strings.DM_SLIDE_1,
    strings.DM_SLIDE_2,
    strings.DM_SLIDE_3,
]


def get_slide_content(index: int) -> str | None:
    """Get content for a carousel slide.

    Args:
        index: 0-indexed slide number

    Returns:
        Slide content string or None if invalid index
    """
    if 0 <= index < len(SLIDES):
        return SLIDES[index]
    return None


def get_total_slides() -> int:
    """Get total number of carousel slides."""
    return len(SLIDES)


def format_validation_errors(results: list) -> str:
    """Format validation errors for display.

    Args:
        results: List of ValidationResult with ok=False

    Returns:
        Formatted string with errors and fix hints
    """
    lines = []
    for r in results:
        if not r.ok:
            lines.append(f"• {r.message}")
            if r.fix_hint:
                lines.append(f"  `{r.fix_hint}`")
    return "\n".join(lines)


def format_validation_warnings(results: list) -> str:
    """Format validation warnings for display.

    Args:
        results: List of ValidationResult with ok=False

    Returns:
        Formatted string with warnings
    """
    lines = []
    for r in results:
        if not r.ok:
            lines.append(f"• {r.message}")
    return "\n".join(lines)
```

**Step 4: Update __init__.py**

```python
# src/codogram/services/dm_onboarding/__init__.py
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
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/services/test_dm_onboarding.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/codogram/services/dm_onboarding/ tests/services/test_dm_onboarding.py
git commit -m "feat(dm): add onboarding service with slides and formatting"
```

---

## Task 6: Dashboard Service

**Files:**
- Create: `src/codogram/services/dashboard.py`
- Test: `tests/services/test_dashboard.py`

**Step 1: Write the failing test**

```python
# tests/services/test_dashboard.py
"""Tests for dashboard service."""
import pytest
from unittest.mock import patch, MagicMock


def test_format_dashboard_empty():
    """Should return empty state message when no projects."""
    from codogram.services.dashboard import format_dashboard

    result = format_dashboard([])

    assert "Пока нет подключённых проектов" in result


def test_format_dashboard_with_projects():
    """Should format projects list."""
    from codogram.services.dashboard import format_dashboard, ProjectInfo

    projects = [
        ProjectInfo(
            chat_name="codogram",
            directory="/home/user/dev/codogram",
            creator="superbereza",
            members=3,
            active_sessions=2,
        ),
    ]

    result = format_dashboard(projects)

    assert "codogram" in result
    assert "/home/user/dev/codogram" in result
    assert "superbereza" in result
    assert "3 участник" in result
    assert "2 сессий" in result


def test_count_active_sessions():
    """Should count total active sessions."""
    from codogram.services.dashboard import count_active_sessions, ProjectInfo

    projects = [
        ProjectInfo("a", "/a", "u", 1, 2),
        ProjectInfo("b", "/b", "u", 1, 3),
    ]

    assert count_active_sessions(projects) == 5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_dashboard.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/codogram/services/dashboard.py
"""Dashboard service for showing all projects."""
from dataclasses import dataclass

from .. import strings


@dataclass
class ProjectInfo:
    """Information about a project for dashboard display."""
    chat_name: str
    directory: str
    creator: str
    members: int
    active_sessions: int


def format_dashboard(projects: list[ProjectInfo]) -> str:
    """Format dashboard message with all projects.

    Args:
        projects: List of ProjectInfo objects

    Returns:
        Formatted dashboard string
    """
    if not projects:
        return strings.DASH_EMPTY

    lines = [strings.DASH_HEADER, ""]

    for i, p in enumerate(projects, 1):
        if p.active_sessions > 0:
            status = strings.DASH_STATUS_ACTIVE.format(count=p.active_sessions)
        else:
            status = strings.DASH_STATUS_INACTIVE

        lines.append(strings.DASH_PROJECT.format(
            num=i,
            chat_name=p.chat_name,
            directory=p.directory,
            creator=p.creator,
            members=p.members,
            status=status,
        ))
        lines.append("")

    total = len(projects)
    active = count_active_sessions(projects)
    lines.append(strings.DASH_FOOTER.format(total=total, active=active))

    return "\n".join(lines)


def count_active_sessions(projects: list[ProjectInfo]) -> int:
    """Count total active Claude sessions across all projects."""
    return sum(p.active_sessions for p in projects)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_dashboard.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/services/dashboard.py tests/services/test_dashboard.py
git commit -m "feat(dm): add dashboard service"
```

---

## Task 7: DM Handler - Router and /start

**Files:**
- Create: `src/codogram/handlers/dm.py`
- Test: `tests/handlers/test_dm.py`

**Step 1: Write the failing test**

```python
# tests/handlers/test_dm.py
"""Tests for DM handlers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_message():
    """Create mock DM message."""
    msg = MagicMock()
    msg.chat.type = "private"
    msg.chat.id = 123456
    msg.from_user.id = 123456
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_telegram_queue():
    """Create mock telegram queue."""
    tq = MagicMock()
    tq.send = AsyncMock()
    tq.edit = AsyncMock()
    return tq


@pytest.mark.asyncio
async def test_dm_start_shows_onboarding_for_new_user(mock_message, mock_telegram_queue):
    """New user should see onboarding flow."""
    from codogram.handlers.dm import handle_dm_start

    with patch("codogram.handlers.dm.get_user_onboarded", return_value=False), \
         patch("codogram.handlers.dm.run_onboarding") as mock_onboarding:
        mock_onboarding.return_value = None

        await handle_dm_start(mock_message, mock_telegram_queue)

        mock_onboarding.assert_called_once()


@pytest.mark.asyncio
async def test_dm_start_shows_mini_status_for_onboarded_user(mock_message, mock_telegram_queue):
    """Onboarded user should see mini status."""
    from codogram.handlers.dm import handle_dm_start

    with patch("codogram.handlers.dm.get_user_onboarded", return_value=True), \
         patch("codogram.handlers.dm.show_mini_status") as mock_status:
        mock_status.return_value = None

        await handle_dm_start(mock_message, mock_telegram_queue)

        mock_status.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/handlers/test_dm.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/codogram/handlers/dm.py
"""DM-specific handlers for onboarding and dashboard."""
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.enums import ChatType

from .. import strings
from ..config import get_user_onboarded, set_user_onboarded, settings
from ..keyboards.dm_onboarding import (
    carousel_keyboard,
    validation_recheck_keyboard,
    dashboard_keyboard,
)
from ..services.dm_onboarding import (
    get_slide_content,
    get_total_slides,
    format_validation_errors,
    format_validation_warnings,
    run_critical_checks,
    run_warning_checks,
)
from ..services.dashboard import format_dashboard, ProjectInfo
from ..session_manager import project_manager
from ..telegram_queue import TelegramQueue

router = Router(name="dm")


# ===== Filters =====

def is_dm(message: Message) -> bool:
    """Check if message is from DM (private chat)."""
    return message.chat.type == ChatType.PRIVATE


def is_admin(message: Message) -> bool:
    """Check if user is admin."""
    return message.from_user.id in settings.get_admin_ids()


# ===== /start in DM =====

@router.message(Command("start"), F.chat.type == ChatType.PRIVATE)
async def cmd_dm_start(message: Message, telegram_queue: TelegramQueue):
    """Handle /start in DM."""
    if not is_admin(message):
        return  # Silently ignore non-admins in DM

    await handle_dm_start(message, telegram_queue)


async def handle_dm_start(message: Message, telegram_queue: TelegramQueue):
    """Main logic for /start in DM."""
    user_id = message.from_user.id

    if get_user_onboarded(user_id):
        await show_mini_status(message, telegram_queue)
    else:
        await run_onboarding(message, telegram_queue)


async def show_mini_status(message: Message, telegram_queue: TelegramQueue):
    """Show mini status for returning users."""
    # Count projects and sessions
    config_projects = project_manager.list_projects()
    project_count = len(config_projects)
    session_count = sum(
        1 for p in config_projects.values()
        if p.get("tmux_session") and p.get("session_id")
    )

    text = strings.DM_MINI_STATUS.format(
        projects=project_count,
        sessions=session_count,
    )
    await telegram_queue.send(message.chat.id, text)


async def run_onboarding(message: Message, telegram_queue: TelegramQueue):
    """Run full onboarding flow."""
    # 1. Welcome message
    await telegram_queue.send(message.chat.id, strings.DM_WELCOME)

    # 2. First slide of carousel
    slide_content = get_slide_content(0)
    keyboard = carousel_keyboard(0, get_total_slides())
    await telegram_queue.send(
        message.chat.id,
        slide_content,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ===== Carousel callbacks =====

@router.callback_query(F.data.startswith("onb:slide:"))
async def on_carousel_slide(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle carousel navigation."""
    if not callback.message:
        await callback.answer()
        return

    # Parse slide number from callback data
    try:
        slide_num = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer("Invalid slide")
        return

    total = get_total_slides()

    # Check if this is the last slide -> show validation
    if slide_num >= total:
        await show_validation(callback, telegram_queue)
        await callback.answer()
        return

    # Show slide
    content = get_slide_content(slide_num)
    if content is None:
        await callback.answer("Invalid slide")
        return

    keyboard = carousel_keyboard(slide_num, total)
    await telegram_queue.edit(
        callback.message,
        content,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await callback.answer()


async def show_validation(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Show validation results after carousel."""
    # Run critical checks
    critical_results = run_critical_checks()
    critical_errors = [r for r in critical_results if not r.ok]

    if critical_errors:
        # Show errors with recheck button
        error_text = format_validation_errors(critical_errors)
        text = strings.DM_VALIDATION_ERROR.format(errors=error_text)
        keyboard = validation_recheck_keyboard()
        await telegram_queue.edit(
            callback.message,
            text,
            reply_markup=keyboard,
        )
        return

    # Run warning checks
    warning_results = run_warning_checks()
    warnings = [r for r in warning_results if not r.ok]

    # Show success + optional warnings + CTA
    bot_info = await callback.bot.get_me()
    cta_text = strings.DM_CTA.format(bot_username=bot_info.username)

    if warnings:
        warning_text = format_validation_warnings(warnings)
        full_text = f"{strings.DM_VALIDATION_OK}\n\n{strings.DM_VALIDATION_WARNINGS.format(warnings=warning_text)}\n\n{cta_text}"
    else:
        full_text = f"{strings.DM_VALIDATION_OK}\n\n{cta_text}"

    await telegram_queue.edit(
        callback.message,
        full_text,
        parse_mode="Markdown",
    )

    # Mark user as onboarded
    set_user_onboarded(callback.from_user.id)


@router.callback_query(F.data == "onb:recheck")
async def on_recheck(callback: CallbackQuery, telegram_queue: TelegramQueue):
    """Handle recheck validation button."""
    if not callback.message:
        await callback.answer()
        return

    await show_validation(callback, telegram_queue)
    await callback.answer()


# ===== /intro =====

@router.message(Command("intro"), F.chat.type == ChatType.PRIVATE)
async def cmd_intro(message: Message, telegram_queue: TelegramQueue):
    """Show onboarding again."""
    if not is_admin(message):
        return

    await run_onboarding(message, telegram_queue)


# ===== /dash =====

@router.message(Command("dash"), F.chat.type == ChatType.PRIVATE)
async def cmd_dash(message: Message, telegram_queue: TelegramQueue, bot: Bot):
    """Show dashboard with all projects."""
    if not is_admin(message):
        return

    await show_dashboard(message.chat.id, telegram_queue, bot)


async def show_dashboard(chat_id: int, telegram_queue: TelegramQueue, bot: Bot):
    """Render and send dashboard."""
    # Gather project info
    projects = []
    for chat_id_str, project_data in project_manager.list_projects().items():
        try:
            chat = await bot.get_chat(int(chat_id_str))
            member_count = await bot.get_chat_member_count(int(chat_id_str))

            # Count active sessions for this project
            active = 1 if project_data.get("session_id") else 0

            # Get creator - might not always be available
            creator = "unknown"
            if hasattr(chat, 'creator') and chat.creator:
                creator = chat.creator.username or str(chat.creator.id)

            projects.append(ProjectInfo(
                chat_name=chat.title or "Untitled",
                directory=project_data.get("cwd", "unknown"),
                creator=creator,
                members=member_count,
                active_sessions=active,
            ))
        except Exception:
            # Skip projects we can't access
            continue

    text = format_dashboard(projects)
    keyboard = dashboard_keyboard()
    await telegram_queue.send(chat_id, text, reply_markup=keyboard)


@router.callback_query(F.data == "dash:refresh")
async def on_dash_refresh(callback: CallbackQuery, telegram_queue: TelegramQueue, bot: Bot):
    """Handle dashboard refresh."""
    if not callback.message:
        await callback.answer()
        return

    await show_dashboard(callback.message.chat.id, telegram_queue, bot)
    await callback.answer("Обновлено")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/handlers/test_dm.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/dm.py tests/handlers/test_dm.py
git commit -m "feat(dm): add DM handler with /start, /intro, /dash"
```

---

## Task 8: Chat Member Handler (Push Notifications)

**Files:**
- Modify: `src/codogram/handlers/dm.py`
- Test: `tests/handlers/test_dm_chat_member.py`

**Step 1: Write the failing test**

```python
# tests/handlers/test_dm_chat_member.py
"""Tests for chat member update handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_chat_member_update():
    """Create mock ChatMemberUpdated event."""
    update = MagicMock()
    update.chat.id = -100123456
    update.chat.title = "Test Project"
    update.chat.type = "supergroup"
    update.from_user.id = 789
    update.from_user.username = "creator"
    update.new_chat_member.status = "administrator"
    update.old_chat_member.status = "left"
    return update


@pytest.mark.asyncio
async def test_bot_added_sends_push_to_admins(mock_chat_member_update):
    """Should send push notification to all admins when bot is added."""
    from codogram.handlers.dm import on_bot_added_to_chat

    mock_bot = MagicMock()
    mock_bot.id = 999
    mock_bot.send_message = AsyncMock()

    with patch("codogram.handlers.dm.settings") as mock_settings:
        mock_settings.get_admin_ids.return_value = {111, 222}

        await on_bot_added_to_chat(mock_chat_member_update, mock_bot)

        assert mock_bot.send_message.call_count == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/handlers/test_dm_chat_member.py -v`
Expected: FAIL

**Step 3: Add to dm.py**

Add to `src/codogram/handlers/dm.py`:

```python
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, ADMINISTRATOR, MEMBER


# ===== Bot added to chat =====

@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> (ADMINISTRATOR | MEMBER))
)
async def on_bot_added_to_chat(event, bot: Bot):
    """Handle bot being added to a chat."""
    # Skip DM
    if event.chat.type == ChatType.PRIVATE:
        return

    chat_name = event.chat.title or "Untitled"
    creator = event.from_user.username or str(event.from_user.id)

    # Try to get invite link
    link = None
    try:
        link = event.chat.invite_link
    except Exception:
        pass

    # Format message
    if link:
        text = strings.DM_BOT_ADDED_WITH_LINK.format(
            chat_name=chat_name,
            link=link,
            creator=creator,
        )
    else:
        text = strings.DM_BOT_ADDED.format(
            chat_name=chat_name,
            creator=creator,
        )

    # Send to all admins
    for admin_id in settings.get_admin_ids():
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            # Admin might have blocked bot or never started DM
            pass
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/handlers/test_dm_chat_member.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codogram/handlers/dm.py tests/handlers/test_dm_chat_member.py
git commit -m "feat(dm): add push notification when bot added to chat"
```

---

## Task 9: Register DM Router in Main

**Files:**
- Modify: `src/codogram/main.py`
- Modify: `src/codogram/handlers/__init__.py`

**Step 1: Add dm router to handlers __init__**

Add to `src/codogram/handlers/__init__.py`:

```python
from .dm import router as dm_router
```

And add to `__all__` list.

**Step 2: Register in main.py**

Find where other routers are included in `src/codogram/main.py` and add:

```python
from .handlers.dm import router as dm_router

# In setup_dispatcher or wherever routers are registered:
dp.include_router(dm_router)
```

**Important:** The DM router should be registered BEFORE the main start router so it catches DM /start first.

**Step 3: Commit**

```bash
git add src/codogram/main.py src/codogram/handlers/__init__.py
git commit -m "feat(dm): register DM router in main"
```

---

## Task 10: Fix Start Handler to Skip DM

**Files:**
- Modify: `src/codogram/handlers/start.py`

**Step 1: Add DM check to existing /start handler**

The existing `/start` handler in `start.py` should skip DM chats since they're now handled by `dm.py`.

Find the `cmd_start` function and add at the beginning:

```python
@router.message(Command("start", ignore_case=True))
async def cmd_start(message: Message, state: FSMContext, telegram_queue: TelegramQueue):
    # Skip DM - handled by dm.py
    if message.chat.type == ChatType.PRIVATE:
        return

    # ... rest of existing code
```

Add import at top:
```python
from aiogram.enums import ChatType
```

**Step 2: Commit**

```bash
git add src/codogram/handlers/start.py
git commit -m "fix(start): skip DM chats, handled by dm router"
```

---

## Task 11: Run All Tests

**Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

**Step 2: Fix any failing tests**

If any tests fail, fix them before proceeding.

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: address test failures"
```

---

## Task 12: E2E Testing

**Files:**
- Reference: `docs/e2e/CLAUDE.md`

**Step 1: Start bot from worktree**

```bash
./kill-instance-and-start-from-worktree.sh
```

**Step 2: Ask user for test chat ID**

Before testing, ask: "Which chat should I use for E2E testing?"

**Step 3: Test /start in DM**

Using Telegram MCP:
```python
mcp__telegram__send_message(chat_id=BOT_DM_ID, message="/start")
mcp__telegram__get_messages(chat_id=BOT_DM_ID, page_size=5)
```

Verify:
- Welcome message appears
- Carousel first slide with "Далее →" button

**Step 4: Test carousel navigation**

```python
mcp__telegram__press_inline_button(chat_id=BOT_DM_ID, button_text="Далее →")
mcp__telegram__get_messages(chat_id=BOT_DM_ID, page_size=3)
```

Verify slides change with ← → navigation.

**Step 5: Test validation**

Navigate to last slide and verify validation runs.

**Step 6: Test /dash**

```python
mcp__telegram__send_message(chat_id=BOT_DM_ID, message="/dash")
mcp__telegram__get_messages(chat_id=BOT_DM_ID, page_size=3)
```

Verify dashboard shows (or empty state).

**Step 7: Test /intro**

```python
mcp__telegram__send_message(chat_id=BOT_DM_ID, message="/intro")
```

Verify onboarding shows again.

**Step 8: Commit E2E test documentation**

Add E2E test cases to `docs/e2e/commands/dm.md` if not exists.

---

## Task 13: Final Cleanup

**Step 1: Run linter**

```bash
ruff check src/codogram/handlers/dm.py src/codogram/services/dm_onboarding/ src/codogram/keyboards/dm_onboarding.py
```

Fix any issues.

**Step 2: Final commit**

```bash
git add -A
git commit -m "chore: cleanup and lint fixes"
```

**Step 3: Update ROADMAP**

If there's a ROADMAP item for this feature, mark it as done.

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | User storage in config | config.py |
| 2 | Validation service | services/dm_onboarding/validation.py |
| 3 | Onboarding strings | strings.py |
| 4 | Carousel/dashboard keyboards | keyboards/dm_onboarding.py |
| 5 | Onboarding service | services/dm_onboarding/onboarding.py |
| 6 | Dashboard service | services/dashboard.py |
| 7 | DM handler | handlers/dm.py |
| 8 | Chat member handler | handlers/dm.py |
| 9 | Register router | main.py |
| 10 | Skip DM in start.py | handlers/start.py |
| 11 | Run all tests | - |
| 12 | E2E testing | - |
| 13 | Final cleanup | - |

Total: 13 tasks, approximately 60-90 minutes implementation time.
