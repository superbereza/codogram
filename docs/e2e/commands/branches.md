# /branch Tests

Branch/worktree creation.

## TC-BRANCHES-001: /branch creates worktree + topic

**Tags:** critical, branches
**Preconditions:** In a git repository forum chat

**Setup:**
```bash
# Ensure clean state
cd /tmp/test-branch-repo
git worktree list
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/branch test-e2e-branch")
# Wait 10s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
mcp__telegram__list_topics(chat_id=-1003356094635)
```

```bash
# Verify worktree
git -C /tmp/test-branch-repo worktree list | grep test-e2e-branch
# Verify branch
git -C /tmp/test-branch-repo branch | grep test-e2e-branch
```

**Expected:**
- UI: Topic created, worktree created
- State:
  - New topic in Telegram
  - Git worktree at `/tmp/test-branch-repo/.worktrees/test-e2e-branch`
  - Git branch `test-e2e-branch`
  - Thread registered with `worktree_path` in config

**Cleanup:**
```bash
# Use /finish to clean up, or manually:
git -C /tmp/test-branch-repo worktree remove .worktrees/test-e2e-branch
git -C /tmp/test-branch-repo branch -D test-e2e-branch
```
