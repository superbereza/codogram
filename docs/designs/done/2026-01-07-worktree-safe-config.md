# Worktree-Safe Config Location

**Date:** 2026-01-07
**Status:** In Progress

## Problem

When `pip install -e .` is run from a worktree, `Path(__file__)` in config.py points to worktree code. This causes:
1. Bot reads/writes config from worktree directory
2. Worktree has empty config → all projects lost
3. Main bot breaks when anyone runs pip install from worktree

## Solution

### 1. Move config to ~/.codogram/

```python
# Before:
CONFIG_PATH = Path(__file__).parent.parent.parent / ".config.json"

# After:
CONFIG_DIR = Path.home() / ".codogram"
CONFIG_PATH = CONFIG_DIR / "config.json"
```

Config location no longer depends on code location.

### 2. dev-run.sh for worktree testing

New script that:
- Uses PYTHONPATH instead of pip install
- Finds .env in current dir or main repo
- Exports env vars before running
- Doesn't pollute venv with worktree code

```bash
# From worktree:
./dev-run.sh  # Uses local src/, main's .env, ~/.codogram/config.json
```

### 3. .env stays in main repo

- Not moved to ~/.codogram/
- dev-run.sh finds it via `../../.env` from worktree
- Simpler, no migration needed

## Migration

1. ✅ Create ~/.codogram/ directory
2. ✅ Copy existing .config.json to ~/.codogram/config.json
3. ✅ Update config.py to use new path
4. ✅ Create dev-run.sh
5. ⬜ Update CLAUDE.md with worktree workflow
6. ⬜ Delete old .config.json from repo root
7. ⬜ Add ~/.codogram/ note to setup docs

## Testing Workflow

```bash
# Main development:
./restart.sh              # Uses pip installed package

# Worktree testing:
cd .worktrees/feature-x/
./dev-run.sh              # Uses PYTHONPATH, kills main bot
# ... test ...
# Return to main:
cd /path/to/main
./restart.sh              # Restores main bot
```

## Files Changed

- `src/codogram/config.py` - CONFIG_PATH → ~/.codogram/
- `dev-run.sh` - New script for worktree testing
- `CLAUDE.md` - Document worktree workflow
