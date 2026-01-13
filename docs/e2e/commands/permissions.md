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

---

## TC-PERMISSIONS-007: MCP trust prompt detected (box-style)

**Tags:** critical, permissions, mcp
**Preconditions:** Project with `.mcp.json` containing untrusted server

**Setup:**
```bash
# Ensure project has .mcp.json with a new MCP server
# The server should NOT be in trusted list yet
cat test-project/.mcp.json
# Should contain an MCP server config

# Kill any existing session to trigger fresh MCP prompt
tmux kill-session -t claude-codogram-test-mcp 2>/dev/null || true
```

**Steps:**
```python
# 1. Start fresh session (triggers MCP trust prompt)
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/start")
# Wait 30s for Claude to show MCP trust prompt

# 2. Check for MCP trust buttons
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Permission buttons appear with MCP server options:
  - "1. Use this and all future MCP servers in this project"
  - "2. Use this MCP server"
  - "3. Continue without using this MCP server"
- State: Prompt parsed as `PromptType.MCP_TRUST`
- Note: Box-style UI with `╭╮╯╰│` characters parsed correctly

---

## TC-PERMISSIONS-008: MCP trust prompt NOT auto-accepted

**Tags:** critical, permissions, mcp, auto_accept
**Preconditions:** auto_accept enabled, MCP trust prompt visible

**Setup:**
```python
# Enable auto_accept
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/auto_accept")
# Wait 2s
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=2)
```

**Steps:**
```python
# 1. Trigger MCP trust prompt (start fresh session with .mcp.json)
# Kill tmux first
# bash: tmux kill-session -t claude-codogram-test-mcp

# 2. Wait 30s for MCP prompt to appear
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
```

**Expected:**
- UI: Permission buttons still visible (NOT auto-accepted)
- State: auto_accept=true in config, but MCP prompts are bypassed
- Log: "Auto-accept: skipping mcp_trust prompt" in logs/codogram.log

**Cleanup:**
```python
# Disable auto_accept
mcp__telegram__send_message(chat_id=TEST_CHAT_ID, message="/auto_accept")
```

---

## TC-PERMISSIONS-009: MCP trust prompt button click works

**Tags:** critical, permissions, mcp
**Preconditions:** MCP trust prompt visible with buttons

**Steps:**
```python
# 1. Find MCP trust buttons
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)

# 2. Click option 2 (Use this MCP server)
mcp__telegram__press_inline_button(chat_id=TEST_CHAT_ID, button_text="2. Use this MCP server")

# 3. Wait 10s for response
mcp__telegram__list_messages(chat_id=TEST_CHAT_ID, limit=5)
```

**Expected:**
- UI: Button click acknowledged, MCP server connected
- State: "2" sent to tmux via send-keys
- Note: Claude proceeds with the selected MCP option

---

## TC-PERMISSIONS-010: Message cancels active permission prompt

**Tags:** critical, permissions
**Preconditions:** Permission prompt visible (Yes/No buttons displayed)

**Context:**
Previously, sending a message while a permission prompt was active would accidentally accept the permission (Enter key selected Yes). This was fixed in commit 671cca0.

**Setup:**
```python
# Trigger permission prompt
mcp__telegram__send_message(chat_id=-1003356094635, message="Run: echo setup test")
# Wait 15s for permission prompt
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
# Should see Yes/No buttons
```

**Steps:**
```python
# Send a new message while permission is active
mcp__telegram__send_message(chat_id=-1003356094635, message="This is a new instruction")
# Wait 5s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: Permission prompt cancelled, new message appears in Claude input
- State:
  - tmux shows message in Claude input (NOT auto-accepted)
  - logs/codogram.log shows "Permission prompt cancelled" or similar
  - Permission buttons disappear from Telegram
- Bug prevention: Message should NOT trigger Yes/No selection

**Verification:**
```bash
# Check tmux - should show new message in prompt area, NOT tool execution
tmux capture-pane -t claude-codogram-testing-area -p | grep "This is a new instruction"
```
