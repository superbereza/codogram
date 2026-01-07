# Permission Poller Tests

Permission button delivery and handling.

## TC-PERMISSIONS-001: Permission buttons in correct topic

**Tags:** smoke, critical, permissions
**Preconditions:** Active session in topic, Claude asking for permission

**Setup:**
```bash
# Ensure session in topic
cat .config.json | jq '.projects["codogram-testing-area"].threads["303"]'
```

**Steps:**
```python
# Ask Claude to do something requiring permission (e.g., run bash)
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Run: echo hello")
# Wait 15s for permission prompt
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Inline buttons (Yes/No or tool options) appear in topic 303
- State: Poller task running for this thread

---

## TC-PERMISSIONS-002: Permission buttons NOT in other topics (isolation)

**Tags:** critical, permissions, isolation
**Preconditions:** Two active topics

**Setup:**
```bash
# Two topics with sessions
# Topic A: 303
# Topic B: 222
```

**Steps:**
```python
# Trigger permission in Topic A
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Run: ls /tmp")
# Wait 15s
# Check Topic B for buttons - should be empty
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=222, limit=3)
# Check Topic A for buttons - should have them
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Permission buttons ONLY in Topic A
- State: Pollers are thread-isolated

---

## TC-PERMISSIONS-003: Button click works

**Tags:** critical, permissions
**Preconditions:** Permission prompt visible

**Steps:**
```python
# Find and click Yes button
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Yes")
# Wait 10s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: Button click acknowledged, tool executes
- State: Permission sent to Claude, execution continues

---

## TC-PERMISSIONS-004: auto_accept works

**Tags:** critical, permissions
**Preconditions:** auto_accept enabled for thread

**Setup:**
```python
# Enable auto_accept
mcp__telegram__send_message(chat_id=-1003356094635, message="/auto_accept")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Steps:**
```python
# Trigger permission
mcp__telegram__send_message(chat_id=-1003356094635, message="Run: echo auto test")
# Wait 15s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: No permission buttons, tool executes automatically
- State: auto_accept=true in config, permission auto-clicked

**Cleanup:**
```python
# Disable auto_accept
mcp__telegram__send_message(chat_id=-1003356094635, message="/auto_accept")
```

---

## TC-PERMISSIONS-005: Poller detects "work in new folder" prompt

**Tags:** critical, permissions, poller
**Preconditions:** Branch topic with worktree, Claude starting fresh

**Setup:**
```bash
# Create new branch topic or use existing one with fresh session
# Kill any existing tmux for this branch
```

**Steps:**
```python
# Start fresh session in branch topic
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=BRANCH_TOPIC_ID, text="/start")
# Wait 30s for Claude to prompt about new folder
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Poller shows "Work in new folder?" or similar prompt with Yes/No buttons
- State: Prompt detected from tmux screen, buttons delivered to correct topic

---

## TC-PERMISSIONS-006: Poller starts for resumed session

**Tags:** critical, permissions, resume
**Preconditions:** Archived topic with session_id, tmux NOT running

**Setup:**
```bash
# Ensure topic is archived and has session_id
cat .config.json | jq '.projects["codogram-testing-area"].threads["TEST_TOPIC"]'
# Should show: "archived": true, "session_id": "xxx"

# Kill tmux if running
tmux kill-session -t claude-codogram-testing-area-TEST_TOPIC 2>/dev/null || true
```

**Steps:**
```python
# 1. Resume session via /start in archived topic
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TEST_TOPIC, text="/start")
# Wait 20s for Claude to start

# 2. Send message that triggers permission
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TEST_TOPIC, text="Run: echo poller test")
# Wait 15s for permission prompt

# 3. Check for permission buttons
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Permission buttons appear in topic (Yes/No)
- State: `thread.poller_task` is not None and not done
- Note: This test verifies poller starts immediately on resume (not just on first message)
