# Phase 9b: Cleanup bot.py - Remove Extracted Handlers

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove duplicate handlers from bot.py that were extracted to handlers/ modules

**Architecture:** Delete duplicate handler functions, keep shared handlers and helpers that handlers/ still depend on

**Tech Stack:** Python, aiogram

---

## Background

### Current State
- `bot.py`: 1802 lines with all handlers
- `handlers/`: 6 modules with extracted handlers (1386 lines total)
- Many handlers are duplicated - bot.py handlers registered on `router`, handlers/ on their own routers
- Both routers registered in main.py (handlers/ first, then bot.py)

### Target State
- `bot.py`: ~300-400 lines (2 shared handlers + helpers)
- All command handling via handlers/ routers
- bot.py's router only for `cb_cancel` and `on_message`

### What to KEEP in bot.py

**Handlers (2) - NOT duplicated, used by handlers/:**
- `cb_cancel` (F.data == "cancel") - generic cancel for branches.py/threads.py buttons
- `on_message` - fallback to forward messages to tmux

**Helpers (4) - imported by handlers/:**
- `require_forum_group` - used by threads.py, branches.py
- `_start_state` - used by threads.py, branches.py
- `_do_branch_create` - used by branches.py
- `_do_branch_cleanup` - used by branches.py

**Infrastructure:**
- `router = Router()` - for the 2 remaining handlers
- imports needed by helpers

### What to REMOVE from bot.py

**Duplicates of handlers/threads.py:**
- `cmd_thread_delete`
- `on_thread_delete_callback`
- `cmd_thread_create`
- `cb_thread_create_confirm` (duplicate of handlers/threads.py:159)

**Duplicates of handlers/branches.py:**
- `cmd_branch_create` and all `bc_*` callbacks
- `cmd_branch_finish` and all `bf_*` callbacks
- `cb_branch_create_redirect` (duplicate of handlers/branches.py:162)

**Duplicates of handlers/sessions.py:**
- `cmd_new`
- `cmd_clear`
- `cmd_esc`
- `cmd_resume`

**Duplicates of handlers/settings.py:**
- `cmd_get_debug_ids`
- `cmd_help`
- `cmd_settings`
- `cmd_auto_accept`

**Duplicates of handlers/start.py:**
- `cmd_start`
- `cmd_restart`
- All `on_start_*` callbacks
- All `on_restart_*` callbacks
- `on_tmux_selected`

---

## Task 1: Remove thread handlers from bot.py

**Delete these functions:**
- `cmd_thread_delete` (~line 404)
- `on_thread_delete_callback` (~line 438)
- `cmd_thread_create` (~line 487)
- `cb_thread_create_confirm` (~line 912) - duplicate of handlers/threads.py

**Keep:** Nothing from threads - all moved to handlers/threads.py

**How to find:** Search for `Command("thread_delete")`, `Command("thread_create")`, `F.data == "thread_create_confirm"`

**Verify:**
```bash
PYTHONPATH=src python -c "from codogram.handlers.threads import router; print('OK')"
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Commit:**
```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove thread handlers (now in handlers/threads.py)"
```

---

## Task 2: Remove branch handlers from bot.py

**Delete these functions:**
- `cmd_branch_create` (~line 765)
- `on_branch_base_selected` (bc_base:)
- `on_branch_create_confirm` (bc_create:)
- `on_branch_commit_request` (bc_commit:)
- `cb_branch_create_redirect` (~line 948) - duplicate
- `cmd_branch_finish` (~line 961)
- `on_branch_merge_selected` (bf_merge:)
- `on_branch_do_merge` (bf_do_merge:)
- `on_branch_delete_selected` (bf_delete:)
- `on_branch_do_delete` (bf_do_delete:)

**Keep:**
- `_do_branch_create` - helper imported by handlers/branches.py
- `_do_branch_cleanup` - helper imported by handlers/branches.py

**How to find:** Search for `Command("branch_create")`, `Command("branch_finish")`, `bc_`, `bf_`

**Verify:**
```bash
PYTHONPATH=src python -c "from codogram.handlers.branches import router; print('OK')"
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Commit:**
```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove branch handlers (now in handlers/branches.py)"
```

---

## Task 3: Remove session handlers from bot.py

**Delete these functions:**
- `cmd_new` (~line 1396)
- `cmd_clear` (~line 1403)
- `cmd_esc` (~line 1214)
- `cmd_resume` (~line 1336)

**Verify:**
```bash
PYTHONPATH=src python -c "from codogram.handlers.sessions import router; print('OK')"
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Commit:**
```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove session handlers (now in handlers/sessions.py)"
```

---

## Task 4: Remove settings handlers from bot.py

**Delete these functions:**
- `cmd_get_debug_ids` (~line 1207)
- `cmd_help` (~line 1237)
- `cmd_settings` (~line 1266)
- `cmd_auto_accept` (~line 1297)

**Verify:**
```bash
PYTHONPATH=src python -c "from codogram.handlers.settings import router; print('OK')"
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Commit:**
```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove settings handlers (now in handlers/settings.py)"
```

---

## Task 5: Remove start/restart handlers from bot.py

**Delete these functions:**
- `cmd_start` (~line 254)
- All `on_start_*` callbacks (create_dir, custom_path, git_init, git_gh, gh_visibility, git_clone, no_git, launch_claude, cancel)
- `on_tmux_selected` (select_tmux:)
- `cmd_restart` (~line 1409)
- `on_restart_confirm` (~line 1457)
- `on_restart_cancel` (~line 1537)

**Keep:**
- `require_forum_group` - helper imported by handlers/
- `_start_state` - state dict imported by handlers/

**Verify:**
```bash
PYTHONPATH=src python -c "from codogram.handlers.start import router; print('OK')"
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -5
```

**Commit:**
```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): remove start/restart handlers (now in handlers/start.py)"
```

---

## Task 6: Final cleanup and verification

**Step 1: Count remaining lines**
```bash
wc -l src/codogram/bot.py
```
Expected: ~300-400 lines

**Step 2: Verify remaining handlers exist**
```bash
grep -n "^@router\." src/codogram/bot.py
```
Expected: Only 2 handlers:
- `@router.callback_query(F.data == "cancel")` → `cb_cancel`
- `@router.message()` → `on_message`

**Step 3: Verify helpers exist**
```bash
grep -n "^def \|^async def " src/codogram/bot.py | head -10
```
Expected: `require_forum_group`, `_start_state`, `_do_branch_create`, `_do_branch_cleanup`, `cb_cancel`, `on_message`

**Step 4: Run full test suite**
```bash
PYTHONPATH=src pytest tests/ -v --tb=short
```

**Step 5: Verify cancel button works**
```bash
# cb_cancel is used by handlers/branches.py and handlers/threads.py
# These modules use callback_data="cancel" buttons
grep -n 'callback_data="cancel"' src/codogram/handlers/*.py
```

**Step 6: Clean up unused imports**
Review imports at top of bot.py - remove any that are no longer needed.

**Commit:**
```bash
git add src/codogram/bot.py
git commit -m "refactor(bot): cleanup unused imports after handler extraction"
```

---

## Summary

**Before:** bot.py ~1802 lines
**After:** bot.py ~300-400 lines

**Removed:** ~20 handler functions (duplicates of handlers/)

**Kept in bot.py:**
- 2 handlers: `cb_cancel`, `on_message`
- 4 helpers: `require_forum_group`, `_start_state`, `_do_branch_create`, `_do_branch_cleanup`
- Router setup

**Next Phase (10):** Extract remaining handlers and helpers from bot.py:
- `cb_cancel` → handlers/common.py
- `on_message` → handlers/messages.py
- helpers → services/
