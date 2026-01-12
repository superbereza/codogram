# /branch Tests

Branch/worktree creation.

## TC-BRANCHES-001: /branch shows name prompt

**Tags:** critical, branches
**Preconditions:** In a git repository forum chat

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/branch")
# Wait 2s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- Message: "Branch name?\n\nSend name or pick random"
- Buttons: [🔮 Magic name], [<<] Go back

## TC-BRANCHES-002: Magic name creates worktree + topic

**Tags:** critical, branches
**Preconditions:** TC-BRANCHES-001 prompt visible

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="🔮 Magic name")
# Wait 10s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
```

```bash
git worktree list
```

**Expected:**
- Prompt deleted
- Worktree created with random name
- Topic created
- "[v] Claude ready" message appears
- Git branch created

## TC-BRANCHES-003: Cancel button deletes prompt

**Tags:** branches
**Preconditions:** /branch prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/branch")
# Wait 1s
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="[<<] Go back")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
```

**Expected:**
- Prompt message deleted
- No worktree/topic created

## TC-BRANCHES-004: Text input creates worktree + topic

**Tags:** critical, branches
**Preconditions:** /branch prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/branch")
# Wait 1s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="my-feature")
# Wait 10s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
```

**Expected:**
- Worktree "my-feature" created
- Topic created
- "[v] Claude ready" message appears

## TC-BRANCHES-005: /branch with argument creates directly

**Tags:** branches, regression
**Preconditions:** In a git repository forum chat

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/branch direct-branch")
# Wait 10s
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
```

**Expected:**
- No prompt shown
- Worktree "direct-branch" created directly
- "[v] Claude ready" message appears

## TC-BRANCHES-006: Uncommitted changes shows options

**Tags:** branches
**Preconditions:** Git repo with uncommitted changes

**Steps:**
```python
# First ensure there are uncommitted changes
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/branch")
# Wait 1s
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="new-branch")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=3)
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- Message: "[!] Uncommitted changes detected"
- Buttons: [Create clean], [Commit first], [<<] Go back

## TC-BRANCHES-007: Branch already exists shows error

**Tags:** branches
**Preconditions:** Branch "main" exists

**Steps:**
```python
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/branch main")
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=2)
```

**Expected:**
- Error: "[x] Branch `main` already exists"
