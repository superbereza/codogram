# Bot.py Refactoring: Phases 1-3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the folder structure and extract first modules (domain/, adapters/) from bot.py without breaking functionality.

**Architecture:** Layer-based architecture with handlers → services → domain flow. Adapters wrap external systems. Each phase is independently deployable.

**Tech Stack:** Python 3.11+, aiogram 3.x, pytest

**Design Doc:** `docs/designs/2025-12-27-bot-refactoring/01-phase-1-3.md`

---

## Phase 1: Create Folder Structure

### Task 1.1: Create directories

**Files:**
- Create: `src/codogram/handlers/__init__.py`
- Create: `src/codogram/services/__init__.py`
- Create: `src/codogram/domain/__init__.py`
- Create: `src/codogram/adapters/__init__.py`
- Create: `src/codogram/middleware/__init__.py`

> **Note:** `keyboards/` not created — conflicts with existing `keyboards.py`. Will migrate in later phase.

**Step 1: Create directories with __init__.py**

```bash
mkdir -p src/codogram/{handlers,services,domain,adapters,middleware}
```

**Step 2: Create empty __init__.py files**

```bash
touch src/codogram/handlers/__init__.py
touch src/codogram/services/__init__.py
touch src/codogram/domain/__init__.py
touch src/codogram/adapters/__init__.py
touch src/codogram/middleware/__init__.py
```

**Step 3: Verify imports work**

```bash
python -c "from codogram import handlers, services, domain, adapters, middleware; print('OK')"
```

Expected: `OK`

**Step 4: Verify bot still starts**

```bash
timeout 5 python -m codogram.main || true
```

Expected: Bot starts, logs "Starting Telegram Bridge"

**Step 5: Commit**

```bash
git add src/codogram/handlers src/codogram/services src/codogram/domain src/codogram/adapters src/codogram/middleware
git commit -m "refactor: create layer folders for bot.py refactoring

Phase 1 of bot.py refactoring - folder structure only.
No behavior changes."
```

---

## Phase 2: Extract domain/

### Task 2.1: Create domain/validators.py with tests

**Files:**
- Create: `src/codogram/domain/validators.py`
- Create: `tests/test_validators.py`

**Step 1: Write the failing test**

Create `tests/test_validators.py`:

```python
"""Tests for domain validators."""
import pytest

from codogram.domain.validators import is_valid_project_name


class TestIsValidProjectName:
    """Tests for is_valid_project_name validator."""

    def test_valid_alphanumeric(self):
        assert is_valid_project_name("myproject") is True

    def test_valid_with_dash(self):
        assert is_valid_project_name("my-project") is True

    def test_valid_with_underscore(self):
        assert is_valid_project_name("my_project") is True

    def test_valid_with_numbers(self):
        assert is_valid_project_name("project123") is True

    def test_valid_mixed(self):
        assert is_valid_project_name("my-project_123") is True

    def test_invalid_empty(self):
        assert is_valid_project_name("") is False

    def test_invalid_with_space(self):
        assert is_valid_project_name("my project") is False

    def test_invalid_with_slash(self):
        assert is_valid_project_name("project/name") is False

    def test_invalid_cyrillic(self):
        assert is_valid_project_name("проект") is False

    def test_invalid_special_chars(self):
        assert is_valid_project_name("project@name") is False
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_validators.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'codogram.domain.validators'`

**Step 3: Write minimal implementation**

Create `src/codogram/domain/validators.py`:

```python
"""Domain validators for project names and other inputs."""
import re


def is_valid_project_name(name: str) -> bool:
    """Check if project name is valid.

    Valid names contain only: letters, digits, dash, underscore.
    """
    if not name:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_validators.py -v
```

Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add src/codogram/domain/validators.py tests/test_validators.py
git commit -m "feat(domain): add is_valid_project_name validator

Extracted from bot.py with full test coverage."
```

---

### Task 2.2: Create domain/states.py

**Files:**
- Create: `src/codogram/domain/states.py`

**Step 1: Create states.py with FSM states**

Create `src/codogram/domain/states.py`:

```python
"""FSM states for conversation flows."""
from aiogram.fsm.state import State, StatesGroup


class StartFlow(StatesGroup):
    """States for /start command flow.

    Additional states will be added in Phase 7 when FSM migration happens.
    """

    awaiting_project_name = State()
    awaiting_dir_choice = State()
    awaiting_git_choice = State()
    awaiting_gh_visibility = State()
    awaiting_clone_url = State()
    awaiting_custom_path = State()
    awaiting_launch_confirm = State()
```

**Step 2: Verify import works**

```bash
python -c "from codogram.domain.states import StartFlow; print(StartFlow.awaiting_project_name)"
```

Expected: `StartFlow:awaiting_project_name`

**Step 3: Commit**

```bash
git add src/codogram/domain/states.py
git commit -m "feat(domain): add FSM states for start flow

Preparation for migrating from _start_state dict to aiogram FSM."
```

---

### Task 2.3: Create domain/models.py

**Files:**
- Create: `src/codogram/domain/models.py`

**Step 1: Create models.py with StartFlowData**

Create `src/codogram/domain/models.py`:

```python
"""Domain models for conversation data."""
from dataclasses import dataclass


@dataclass
class StartFlowData:
    """Data stored during /start flow.

    Additional fields (tmux_name, thread_id) will be added in Phase 7
    when FSM migration happens.
    """

    project: str | None = None
    path: str | None = None
```

**Step 2: Verify import works**

```bash
python -c "from codogram.domain.models import StartFlowData; print(StartFlowData())"
```

Expected: `StartFlowData(project=None, path=None)`

**Step 3: Commit**

```bash
git add src/codogram/domain/models.py
git commit -m "feat(domain): add StartFlowData model

Data class for FSM state storage during /start flow."
```

---

### Task 2.4: Create domain/errors.py

**Files:**
- Create: `src/codogram/domain/errors.py`

**Step 1: Create errors.py with base exception**

Create `src/codogram/domain/errors.py`:

```python
"""Domain errors and exceptions."""


class CodogramError(Exception):
    """Base exception for all Codogram errors.

    Specific exceptions will be added as needed (YAGNI).
    """

    pass
```

**Step 2: Verify import works**

```bash
python -c "from codogram.domain.errors import CodogramError; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/codogram/domain/errors.py
git commit -m "feat(domain): add CodogramError base exception"
```

---

### Task 2.5: Update domain/__init__.py exports

**Files:**
- Modify: `src/codogram/domain/__init__.py`

**Step 1: Add exports to __init__.py**

Update `src/codogram/domain/__init__.py`:

```python
"""Domain layer - models, validators, states, errors."""
from .validators import is_valid_project_name
from .states import StartFlow
from .models import StartFlowData
from .errors import CodogramError

__all__ = [
    "is_valid_project_name",
    "StartFlow",
    "StartFlowData",
    "CodogramError",
]
```

**Step 2: Verify imports work**

```bash
python -c "from codogram.domain import is_valid_project_name, StartFlow, StartFlowData, CodogramError; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/codogram/domain/__init__.py
git commit -m "refactor(domain): export public API from __init__"
```

---

### Task 2.6: Update bot.py to use domain/validators

**Files:**
- Modify: `src/codogram/bot.py:52-57`

**Step 1: Find current is_valid_project_name in bot.py**

```bash
grep -n "def is_valid_project_name" src/codogram/bot.py
```

Expected: Line ~52

**Step 2: Add import at top of bot.py**

Add after other imports (around line 31):

```python
from .domain.validators import is_valid_project_name
```

**Step 3: Remove local definition from bot.py**

Delete lines 52-57 (the `def is_valid_project_name` function).

**Step 4: Run tests to verify nothing broke**

```bash
pytest tests/test_validators.py -v
```

Expected: All tests PASS

**Step 5: Verify bot starts**

```bash
timeout 5 python -m codogram.main || true
```

Expected: Bot starts normally

**Step 6: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): use domain.validators.is_valid_project_name

First extraction from bot.py to domain layer."
```

---

## Phase 3: Extract adapters/telegram.py

### Task 3.1: Create adapters/telegram.py with tests

**Files:**
- Create: `src/codogram/adapters/telegram.py`
- Create: `tests/test_telegram_adapter.py`

**Step 1: Write the failing test**

Create `tests/test_telegram_adapter.py`:

```python
"""Tests for Telegram adapter."""
import pytest
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramRetryAfter

from codogram.adapters.telegram import send_with_retry


class TestSendWithRetry:
    """Tests for send_with_retry function."""

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        """Message sent successfully on first attempt."""
        mock_bot = AsyncMock()

        result = await send_with_retry(mock_bot, 123, "test message")

        assert result is True
        mock_bot.send_message.assert_called_once_with(
            123,
            "test message",
            parse_mode="Markdown",
            message_thread_id=None,
        )

    @pytest.mark.asyncio
    async def test_success_with_thread_id(self):
        """Message sent to specific thread."""
        mock_bot = AsyncMock()

        result = await send_with_retry(
            mock_bot, 123, "test", message_thread_id=456
        )

        assert result is True
        mock_bot.send_message.assert_called_once_with(
            123,
            "test",
            parse_mode="Markdown",
            message_thread_id=456,
        )

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """Retries on rate limit and succeeds."""
        mock_bot = AsyncMock()
        # TelegramRetryAfter requires: method, message, retry_after
        error = TelegramRetryAfter(
            method=None,
            message="Rate limited",
            retry_after=0,  # Don't actually wait in tests
        )
        mock_bot.send_message.side_effect = [error, None]

        result = await send_with_retry(mock_bot, 123, "test", retries=2)

        assert result is True
        assert mock_bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_fail_after_max_retries(self):
        """Returns False after exhausting retries."""
        mock_bot = AsyncMock()
        error = TelegramRetryAfter(
            method=None,
            message="Rate limited",
            retry_after=0,
        )
        mock_bot.send_message.side_effect = error

        result = await send_with_retry(mock_bot, 123, "test", retries=2)

        assert result is False
        assert mock_bot.send_message.call_count == 2
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_telegram_adapter.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

Create `src/codogram/adapters/telegram.py`:

```python
"""Telegram adapter - messaging utilities."""
import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from ..logging_config import logger


async def send_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    message_thread_id: int | None = None,
    retries: int = 3,
) -> bool:
    """Send message with retry on rate limit.

    Args:
        bot: Telegram bot instance
        chat_id: Target chat ID
        text: Message text
        parse_mode: Telegram parse mode
        message_thread_id: Thread/topic ID if any
        retries: Max retry attempts

    Returns:
        True if sent successfully, False otherwise
    """
    for attempt in range(retries):
        try:
            await bot.send_message(
                chat_id,
                text,
                parse_mode=parse_mode,
                message_thread_id=message_thread_id,
            )
            return True
        except TelegramRetryAfter as e:
            logger.warning(
                f"Rate limited, retrying in {e.retry_after}s "
                f"(attempt {attempt + 1}/{retries})"
            )
            await asyncio.sleep(e.retry_after + 1)

    logger.error("Failed to send message after retries")
    return False
```

**Step 4: Run tests**

```bash
pytest tests/test_telegram_adapter.py -v
```

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/codogram/adapters/telegram.py tests/test_telegram_adapter.py
git commit -m "feat(adapters): add send_with_retry to telegram adapter

Extracted from bot.py with full test coverage."
```

---

### Task 3.2: Update adapters/__init__.py

**Files:**
- Modify: `src/codogram/adapters/__init__.py`

**Step 1: Add exports**

Update `src/codogram/adapters/__init__.py`:

```python
"""Adapters layer - external system wrappers."""
from .telegram import send_with_retry

__all__ = ["send_with_retry"]
```

**Step 2: Verify import**

```bash
python -c "from codogram.adapters import send_with_retry; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/codogram/adapters/__init__.py
git commit -m "refactor(adapters): export public API from __init__"
```

---

### Task 3.3: Update bot.py to use adapters/telegram

**Files:**
- Modify: `src/codogram/bot.py`

**Step 1: Find all send_with_retry usages in bot.py**

```bash
grep -n "send_with_retry" src/codogram/bot.py
```

Note: We'll update calls AND remove the local function definition.

**Step 2: Add import at top of bot.py**

Add after domain import:

```python
from .adapters.telegram import send_with_retry
```

**Step 3: Remove local send_with_retry function**

Delete the local `async def send_with_retry(...)` function (around lines 60-84).

**Step 4: Update all calls to new signature**

Old signature: `send_with_retry(message, text, ...)`
New signature: `send_with_retry(message.bot, message.chat.id, text, ...)`

Find and replace each call. Example:
```python
# Before:
await send_with_retry(message, "text", message_thread_id=thread_id)

# After:
await send_with_retry(message.bot, message.chat.id, "text", message_thread_id=thread_id)
```

**Step 5: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS

**Step 6: Verify bot starts**

```bash
timeout 5 python -m codogram.main || true
```

Expected: Bot starts normally

**Step 7: Commit**

```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): use adapters.telegram.send_with_retry

Removed local function, updated all calls to new signature."
```

---

## Phase 1-3 Complete: Verification

### Final Checklist

Run all checks:

```bash
# 1. All tests pass
pytest tests/ -v

# 2. Imports work
python -c "
from codogram.domain import is_valid_project_name, StartFlow, StartFlowData, CodogramError
from codogram.adapters import send_with_retry
print('All imports OK')
"

# 3. Bot starts
timeout 5 python -m codogram.main || true
```

### Summary Commit

```bash
git add .
git commit -m "refactor: complete phases 1-3 of bot.py refactoring

- Phase 1: Created layer folders (handlers/, services/, domain/, adapters/, middleware/)
- Phase 2: Extracted domain/ (validators, states, models, errors)
- Phase 3: Extracted adapters/telegram.py (send_with_retry)

bot.py still works, first modules extracted with tests."
```

---

## Files Created/Modified

| File | Action | Lines |
|------|--------|-------|
| `src/codogram/handlers/__init__.py` | Create | 0 |
| `src/codogram/services/__init__.py` | Create | 0 |
| `src/codogram/domain/__init__.py` | Create | ~12 |
| `src/codogram/domain/validators.py` | Create | ~12 |
| `src/codogram/domain/states.py` | Create | ~15 |
| `src/codogram/domain/models.py` | Create | ~12 |
| `src/codogram/domain/errors.py` | Create | ~10 |
| `src/codogram/adapters/__init__.py` | Create | ~5 |
| `src/codogram/adapters/telegram.py` | Create | ~45 |
| `src/codogram/middleware/__init__.py` | Create | 0 |
| `tests/test_validators.py` | Create | ~40 |
| `tests/test_telegram_adapter.py` | Create | ~65 |
| `src/codogram/bot.py` | Modify | -30 |

**Total:** 12 new files, 1 modified, ~185 lines added
