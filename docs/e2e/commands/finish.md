# /finish Tests

Topic archiving and branch merging.

## TC-FINISH-001: /finish archives topic

**Tags:** critical, finish
**Preconditions:** Regular topic (not a branch)

**Setup:**
```bash
# Find a regular topic to archive
cat .config.json | jq '.projects["codogram-testing-area"].threads | to_entries | .[] | select(.value.worktree_path == null and .value.archived != true)'
```

**Steps:**
```python
# In regular topic (e.g., 303)
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="/finish")
# Wait 3s
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
# Select archive option
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Archive")
# Wait 5s
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=303, limit=3)
```

**Expected:**
- UI: Archive confirmation
- State: `archived: true` in config, topic closed in Telegram

---

## TC-FINISH-002: /finish merges branch

**Tags:** critical, finish, branches
**Preconditions:** Branch topic with worktree

**Setup:**
```bash
# Find branch topic
cat .config.json | jq '.projects["codogram-testing-area"].threads | to_entries | .[] | select(.value.worktree_path != null and .value.archived != true)'
# Ensure some commits on branch
cd /tmp/test-branch-repo/.worktrees/test-resume
echo "test" > test-merge.txt
git add . && git commit -m "test commit"
```

**Steps:**
```python
# In branch topic (e.g., 222)
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=222, text="/finish")
# Wait 3s
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
# Select merge option
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Merge")
# Wait 10s
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=222, limit=5)
```

**Expected:**
- UI: Merge success message
- State:
  - Branch merged to base_branch
  - Worktree removed
  - Topic archived
  - `archived: true` in config
