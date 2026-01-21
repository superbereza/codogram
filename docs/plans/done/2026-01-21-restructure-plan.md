# Project Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reorganize `src/codogram/` into provider-based folders (`telegram/`, `tmux/`, `claude/`, `git/`, `core/`) for better navigation.

**Architecture:** Move files into logical groups by external system (Telegram, tmux, Claude CLI, git). Keep `handlers/`, `services/`, `domain/`, `middleware/` unchanged. Update all imports after each move.

**Tech Stack:** Python, aiogram, git mv

**Import convention:** Codebase uses relative imports (`.module`, `..module`). Update patterns accordingly.

---

## Task 1: Create folder structure

**Files:**
- Create: `src/codogram/telegram/__init__.py`
- Create: `src/codogram/tmux/__init__.py`
- Create: `src/codogram/claude/__init__.py`
- Create: `src/codogram/git/__init__.py`
- Create: `src/codogram/core/__init__.py`

**Step 1: Create directories and __init__.py files**

```bash
mkdir -p src/codogram/telegram src/codogram/tmux src/codogram/claude src/codogram/git src/codogram/core
touch src/codogram/telegram/__init__.py
touch src/codogram/tmux/__init__.py
touch src/codogram/claude/__init__.py
touch src/codogram/git/__init__.py
touch src/codogram/core/__init__.py
```

**Step 2: Verify structure**

Run: `find src/codogram -type d | sort`
Expected: New folders appear in list

**Step 3: Commit**

```bash
git add src/codogram/telegram src/codogram/tmux src/codogram/claude src/codogram/git src/codogram/core
git commit -m "chore: create folder structure for restructure"
```

---

## Task 2: Move telegram/ files

**Files:**
- Move: `src/codogram/telegram_queue.py` → `src/codogram/telegram/queue.py`
- Move: `src/codogram/adapters/telegram.py` → `src/codogram/telegram/adapters.py`
- Move: `src/codogram/adapters/sticker.py` → `src/codogram/telegram/sticker.py`
- Move: `src/codogram/launch_animation.py` → `src/codogram/telegram/launch_animation.py`
- Move: `src/codogram/keyboards/` → `src/codogram/telegram/keyboards/`
- Move: `src/codogram/tmux_selector.py` → `src/codogram/telegram/keyboards/tmux_selector.py`

**Step 1: Move files with git mv**

```bash
git mv src/codogram/telegram_queue.py src/codogram/telegram/queue.py
git mv src/codogram/adapters/telegram.py src/codogram/telegram/adapters.py
git mv src/codogram/adapters/sticker.py src/codogram/telegram/sticker.py
git mv src/codogram/launch_animation.py src/codogram/telegram/launch_animation.py
git mv src/codogram/keyboards src/codogram/telegram/keyboards
git mv src/codogram/tmux_selector.py src/codogram/telegram/keyboards/tmux_selector.py
```

**Step 2: Find imports to update**

```bash
# telegram_queue imports
grep -rn "from.*telegram_queue" src/codogram/
grep -rn "import.*telegram_queue" src/codogram/

# adapters imports
grep -rn "from.*adapters" src/codogram/

# launch_animation imports
grep -rn "from.*launch_animation" src/codogram/

# keyboards imports
grep -rn "from.*keyboards" src/codogram/

# tmux_selector imports
grep -rn "from.*tmux_selector" src/codogram/
```

**Step 3: Update imports**

Pattern replacements (relative imports):
- In `src/codogram/*.py`: `from .telegram_queue` → `from .telegram.queue`
- In `src/codogram/handlers/*.py`: `from ..telegram_queue` → `from ..telegram.queue`
- In `src/codogram/services/*.py`: `from ..telegram_queue` → `from ..telegram.queue`
- In `src/codogram/middleware/*.py`: `from ..telegram_queue` → `from ..telegram.queue`
- `from .adapters.telegram` → `from .telegram.adapters`
- `from .adapters.sticker` → `from .telegram.sticker`
- `from .launch_animation` → `from .telegram.launch_animation`
- `from ..launch_animation` → `from ..telegram.launch_animation`
- `from .keyboards` → `from .telegram.keyboards`
- `from ..keyboards` → `from ..telegram.keyboards`
- `from ...keyboards` → `from ...telegram.keyboards`
- `from ..tmux_selector` → `from ..telegram.keyboards.tmux_selector`

**Step 4: Remove empty adapters/ folder**

```bash
rm src/codogram/adapters/__init__.py
rmdir src/codogram/adapters
```

**Step 5: Verify imports**

Run: `python -c "import codogram.main" && echo "✓ imports ok"`
Expected: `✓ imports ok`

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move telegram-related files to telegram/"
```

---

## Task 3: Move tmux/ files

**Files:**
- Move: `src/codogram/tmux.py` → `src/codogram/tmux/session.py`
- Move: `src/codogram/project_launcher.py` → `src/codogram/tmux/launcher.py`

**Step 1: Move files with git mv**

```bash
git mv src/codogram/tmux.py src/codogram/tmux/session.py
git mv src/codogram/project_launcher.py src/codogram/tmux/launcher.py
```

**Step 2: Find imports to update**

```bash
grep -rn "from.*\.tmux import" src/codogram/
grep -rn "from.*project_launcher" src/codogram/
```

**Step 3: Update imports**

Pattern replacements:
- `from .tmux import TmuxSession` → `from .tmux.session import TmuxSession`
- `from .tmux import find_all_tmux_by_cwd, find_tmux_by_convention, TmuxSession, kill_tmux_session` → `from .tmux.session import find_all_tmux_by_cwd, find_tmux_by_convention, TmuxSession, kill_tmux_session`
- `from ..tmux import TmuxSession` → `from ..tmux.session import TmuxSession`
- `from .project_launcher import` → `from .tmux.launcher import`
- `from ..project_launcher import` → `from ..tmux.launcher import`

**Step 4: Verify imports**

Run: `python -c "import codogram.main" && echo "✓ imports ok"`
Expected: `✓ imports ok`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move tmux-related files to tmux/"
```

---

## Task 4: Move claude/ files

**Files:**
- Move: `src/codogram/screen.py` → `src/codogram/claude/screen.py`
- Move: `src/codogram/history_reader.py` → `src/codogram/claude/session_finder.py`
- Move: `src/codogram/watcher.py` → `src/codogram/claude/history_watcher.py`
- Move: `src/codogram/permission_poller.py` → `src/codogram/claude/poller.py`

**Step 1: Move files with git mv**

```bash
git mv src/codogram/screen.py src/codogram/claude/screen.py
git mv src/codogram/history_reader.py src/codogram/claude/session_finder.py
git mv src/codogram/watcher.py src/codogram/claude/history_watcher.py
git mv src/codogram/permission_poller.py src/codogram/claude/poller.py
```

**Step 2: Find imports to update**

```bash
grep -rn "from.*\.screen import" src/codogram/
grep -rn "from.*history_reader" src/codogram/
grep -rn "from.*\.watcher import" src/codogram/
grep -rn "from.*permission_poller" src/codogram/
```

**Step 3: Update imports**

Pattern replacements:
- `from .screen import` → `from .claude.screen import`
- `from ..screen import` → `from ..claude.screen import`
- `from .history_reader import` → `from .claude.session_finder import`
- `from ..history_reader import` → `from ..claude.session_finder import`
- `from .watcher import` → `from .claude.history_watcher import`
- `from .permission_poller import` → `from .claude.poller import`

**Step 4: Verify imports**

Run: `python -c "import codogram.main" && echo "✓ imports ok"`
Expected: `✓ imports ok`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move claude-related files to claude/"
```

---

## Task 5: Move git/ files

**Files:**
- Move: `src/codogram/git_utils.py` → `src/codogram/git/utils.py`
- Move: `src/codogram/worktree.py` → `src/codogram/git/worktree.py`
- Move: `src/codogram/project_resolver.py` → `src/codogram/git/resolver.py`

**Step 1: Move files with git mv**

```bash
git mv src/codogram/git_utils.py src/codogram/git/utils.py
git mv src/codogram/worktree.py src/codogram/git/worktree.py
git mv src/codogram/project_resolver.py src/codogram/git/resolver.py
```

**Step 2: Find imports to update**

```bash
grep -rn "from.*git_utils" src/codogram/
grep -rn "from.*\.worktree import" src/codogram/
grep -rn "from.*project_resolver" src/codogram/
```

**Step 3: Update imports**

Pattern replacements:
- `from .git_utils import` → `from .git.utils import`
- `from ..git_utils import` → `from ..git.utils import`
- `from .worktree import` → `from .git.worktree import`
- `from ..worktree import` → `from ..git.worktree import`
- `from .project_resolver import` → `from .git.resolver import`

**Step 4: Verify imports**

Run: `python -c "import codogram.main" && echo "✓ imports ok"`
Expected: `✓ imports ok`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move git-related files to git/"
```

---

## Task 6: Move core/ files

**Files:**
- Move: `src/codogram/session_manager.py` → `src/codogram/core/session_manager.py`
- Move: `src/codogram/history_watcher.py` → `src/codogram/core/coordinator.py`

**Step 1: Move files with git mv**

```bash
git mv src/codogram/session_manager.py src/codogram/core/session_manager.py
git mv src/codogram/history_watcher.py src/codogram/core/coordinator.py
```

**Step 2: Find imports to update**

```bash
grep -rn "from.*session_manager" src/codogram/
grep -rn "from.*history_watcher" src/codogram/
```

**Step 3: Update imports**

Pattern replacements:
- `from .session_manager import` → `from .core.session_manager import`
- `from ..session_manager import` → `from ..core.session_manager import`
- `from .history_watcher import` → `from .core.coordinator import`

**Step 4: Verify imports**

Run: `python -c "import codogram.main" && echo "✓ imports ok"`
Expected: `✓ imports ok`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move core files to core/"
```

---

## Task 7: Final verification and tests

**Step 1: Run pytest**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 2: Commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: resolve any remaining import issues"
```

---

## Task 8: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Move: `docs/designs/2026-01-21-restructure-design.md` → `docs/designs/done/`

**Step 1: Update CLAUDE.md Key files section**

Replace the "Key files" section with new structure:

```
## Key files

src/codogram/
├── main.py                   # Bot entry point
├── config.py                 # Settings + config persistence
├── strings.py                # All UI texts
│
├── telegram/                 # Telegram: message queue, keyboards, launch animation
│   ├── queue.py
│   ├── adapters.py
│   ├── sticker.py
│   ├── launch_animation.py
│   └── keyboards/
│       └── tmux_selector.py  # Tmux selection keyboard
│
├── tmux/                     # Tmux: sessions, commands, window creation
│   ├── session.py
│   └── launcher.py
│
├── claude/                   # Claude CLI: screen parsing, permission prompts, history.jsonl
│   ├── screen.py
│   ├── session_finder.py
│   ├── history_watcher.py
│   └── poller.py
│
├── git/                      # Git: worktree, branches, utils
│   ├── utils.py
│   ├── worktree.py
│   └── resolver.py           # Project name resolution
│
├── core/                     # Core: project state, background task coordinator
│   ├── session_manager.py
│   └── coordinator.py
│
├── domain/                   # Data models, FSM states, validators
├── handlers/                 # Telegram commands (/start, /new_chat, etc.)
├── services/                 # Business logic (start flow, message routing, launch)
└── middleware/               # Authorization
```

**Step 2: Move design to done/**

```bash
git mv docs/designs/2026-01-21-restructure-design.md docs/designs/done/
```

**Step 3: Commit**

```bash
git add -A
git commit -m "docs: update CLAUDE.md with new structure, move design to done"
```

---

## Task 9: Manual bot test (requires user confirmation)

**Step 1: Ask user for permission**

Ask: "Can I start the bot from worktree for manual testing?"

**Step 2: If confirmed, start bot**

```bash
./kill-instance-and-start-from-worktree.sh
```

**Step 3: Test basic functionality**

- Send `/help` command
- Check logs for errors: `tail -f logs/codogram.log`

**Step 4: Stop bot (Ctrl+C) and restore main**

```bash
cd /home/superbereza/dev/codogram
./stop-and-restart.sh
```

---

## Task 10: Merge to main

**Step 1: Push branch**

```bash
git push -u origin restructure
```

**Step 2: Merge (after PR review or direct merge)**

```bash
cd /home/superbereza/dev/codogram
git merge restructure
./stop-and-restart.sh
```
