# Bug: /finish and /resume crash on stale worktree_path

**Date:** 2026-01-12
**Severity:** High
**Status:** Active

## Summary

When a worktree is deleted externally (e.g., after merging a branch), but the Telegram topic still exists, commands like `/finish` and `/resume` crash because they try to access a non-existent directory.

## Reproduction

1. Create a branch with `/branch my-feature`
2. Work on the feature, merge to main
3. Delete worktree: `git worktree remove .worktrees/my-feature`
4. Delete branch: `git branch -d my-feature`
5. Go to the Telegram topic for `my-feature`
6. Run `/finish`

**Result:** Bot crashes with `FileNotFoundError`

## Error

```
FileNotFoundError: [Errno 2] No such file or directory:
PosixPath('/home/superbereza/dev/codogram/.worktrees/topic-create-ux')
```

**Location:** `finish.py:72` calling `has_uncommitted_changes(worktree_path)` in `git_utils.py:70`

## Root Cause

The thread config stores `worktree_path` pointing to a directory that no longer exists. Commands assume the path is valid without checking.

## Affected Commands

- `/finish` - crashes when checking uncommitted changes
- `/resume` - would crash when trying to start Claude in non-existent directory

## Proposed Fix

**Option A (recommended):** Check path existence before operations:
```python
if thread.worktree_path and Path(thread.worktree_path).exists():
    # worktree logic
else:
    # treat as regular topic
```

**Option B:** Clear worktree_path when path doesn't exist (loses history)

**Option C:** Don't allow worktree deletion while topic exists (restricts workflow)

## Workaround

Manually archive the topic in Telegram, or edit `~/.codogram/config.json` to remove the thread entry.
