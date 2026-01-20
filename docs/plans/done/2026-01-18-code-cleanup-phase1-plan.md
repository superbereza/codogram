# Code Cleanup Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix circular dependency and extract magic numbers to constants.

**Architecture:** Replace direct `main.telegram_queue` import with aiogram DI, add constants to config.py.

**Tech Stack:** Python, aiogram DI

---

## Task 1: Fix Circular Dependency in messages.py

**Files:**
- Modify: `src/codogram/handlers/messages.py:164-185`

**Step 1: Read current implementation**

Read `src/codogram/handlers/messages.py` lines 160-190 to understand context.

**Step 2: Replace main import with DI parameter**

Change function `_start_binding` to accept `telegram_queue` from caller:

```python
# BEFORE (line 164-185):
async def _start_binding(message: Message, result):
    from .. import main
    ...
    main.telegram_queue

# AFTER:
async def _start_binding(message: Message, result, telegram_queue: "TelegramQueue"):
    ...
    telegram_queue  # use parameter instead
```

**Step 3: Update caller to pass telegram_queue**

Find where `_start_binding` is called and pass `telegram_queue` from handler's `data` dict.

**Step 4: Run tests**

```bash
pytest tests/ -v --tb=short -x
```

**Step 5: Manual test**

Restart bot, send message in a topic, verify it works.

```bash
./stop-and-restart.sh
```

**Step 6: Commit**

```bash
git add src/codogram/handlers/messages.py
git commit -m "fix: remove circular dependency in messages.py

Use aiogram DI instead of importing main.telegram_queue directly."
```

---

## Task 2: Extract Magic Numbers to Constants

**Files:**
- Modify: `src/codogram/config.py` (add constants)
- Modify: `src/codogram/telegram_queue.py:274`
- Modify: `src/codogram/chunker.py:2`
- Modify: `src/codogram/screen.py:257`
- Modify: `src/codogram/tmux.py:91`

**Step 1: Add constants to config.py**

```python
# Telegram limits
TELEGRAM_MESSAGE_MAX_LENGTH = 4000

# Screen parsing
SCREEN_SEPARATOR_MIN_DASHES = 10

# Tmux capture
TMUX_CAPTURE_LINES_DEFAULT = 30
```

**Step 2: Update telegram_queue.py**

```python
# Line 274: replace 4000 with constant
from .config import TELEGRAM_MESSAGE_MAX_LENGTH

if len(text) > TELEGRAM_MESSAGE_MAX_LENGTH:
```

**Step 3: Update chunker.py**

```python
# Line 2: replace default 4000 with constant
from .config import TELEGRAM_MESSAGE_MAX_LENGTH

def chunk_message(text: str, max_len: int = TELEGRAM_MESSAGE_MAX_LENGTH) -> list[str]:
```

**Step 4: Update screen.py**

```python
# Line 257: replace '─' * 10 with constant
from .config import SCREEN_SEPARATOR_MIN_DASHES

if '─' * SCREEN_SEPARATOR_MIN_DASHES in line:
```

**Step 5: Update tmux.py**

```python
# Line 91: replace -30 with constant
from .config import TMUX_CAPTURE_LINES_DEFAULT

["tmux", "capture-pane", "-t", self.name, "-p", "-S", f"-{TMUX_CAPTURE_LINES_DEFAULT}"],
```

**Step 6: Run tests**

```bash
pytest tests/ -v --tb=short
```

**Step 7: Commit**

```bash
git add src/codogram/config.py src/codogram/telegram_queue.py src/codogram/chunker.py src/codogram/screen.py src/codogram/tmux.py
git commit -m "refactor: extract magic numbers to constants

- TELEGRAM_MESSAGE_MAX_LENGTH = 4000
- SCREEN_SEPARATOR_MIN_DASHES = 10
- TMUX_CAPTURE_LINES_DEFAULT = 30"
```

---

## Task 3: Update Design Doc and Push

**Step 1: Update design doc status**

Edit `docs/plans/2026-01-18-code-cleanup-design.md`:
- Change Phase 1 status from "In Progress" to "Done"

**Step 2: Commit and push**

```bash
git add docs/plans/2026-01-18-code-cleanup-design.md
git commit -m "docs: mark Phase 1 as done"
git push
```

---

## Estimated Time

- Task 1: ~5 min
- Task 2: ~10 min
- Task 3: ~2 min

**Total: ~17 min**
