# Recreate worktree fails on stale git registration

**Найден в тесте:** R6
**Severity:** minor
**Status:** active

## Воспроизведение

1. Создать branch topic с worktree
2. Удалить worktree вручную: `rm -rf .worktrees/branch-name`
3. /start в topic
4. Нажать "Recreate worktree"

## Ожидаемый результат

Worktree пересоздаётся

## Фактический результат

```
[x] Failed to recreate: fatal: '/tmp/test-branch-repo/.worktrees/test-resume' is a missing but already registered worktree;
use 'add -f' to override, or 'prune' or 'remove' to clear
```

## Причина

Git хранит регистрацию worktree даже после удаления папки.
Нужен `git worktree prune` перед `git worktree add`.

## Фикс

`src/codogram/handlers/start.py:676`:
```python
# Before adding, prune stale worktrees
await asyncio.to_thread(
    subprocess.run,
    ["git", "worktree", "prune"],
    cwd=str(main_repo),
)

# Then add the worktree
result = await asyncio.to_thread(
    subprocess.run,
    ["git", "worktree", "add", str(worktree_path), branch_name],
    ...
)
```

Или использовать флаг `-f`:
```python
["git", "worktree", "add", "-f", str(worktree_path), branch_name]
```
