# /start, /reset_chat Tests

## TC-START-001: /start connects to existing tmux

**Tags:** smoke, critical, start
**Preconditions:** tmux session exists with matching name

**Setup:**
```bash
tmux new-session -d -s claude-codogram-testing-area -c /tmp/test-branch-repo
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/start")
# Wait 5s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=3)
```

**Expected:**
- UI: Response contains "Connected to claude-codogram-testing-area"
- State: Bot is monitoring the tmux session

---

## TC-START-002: /start launches Claude when no tmux

**Tags:** critical, start
**Preconditions:** No tmux session for project

**Setup:**
```bash
tmux kill-session -t claude-codogram-testing-area 2>/dev/null || true
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/start")
# Wait 20s for Claude to launch
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: Animation faces, then "Connected" or session bound message
- State: `tmux has-session -t claude-codogram-testing-area` returns 0

---

## TC-START-003: /start in topic

**Tags:** critical, start
**Preconditions:** Topic exists (e.g., thread_id=303)

**Setup:**
```bash
# Ensure topic exists in chat
mcp__telegram__list_topics(chat_id=-1003356094635)
# Kill topic's tmux if exists
tmux kill-session -t claude-codogram-testing-area-test-regular-topic 2>/dev/null || true
```

**Steps:**
```python
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="/start")
# Wait 20s
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=303, limit=5)
```

**Expected:**
- UI: Response in topic, contains "Connected" or session bound
- State: tmux session named `claude-codogram-testing-area-{topic_name}`

---

## TC-START-004: /start resume in General

**Tags:** critical, start, resume
**Preconditions:** session_id exists, tmux killed

**Setup:**
```bash
# Get session_id from config
cat .config.json | jq '.projects["codogram-testing-area"].threads["null"].session_id'
# Kill tmux
tmux kill-session -t claude-codogram-testing-area 2>/dev/null || true
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/start")
# Wait 3s for menu
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
# Press Resume
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Resume")
# Wait 20s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: Menu with Resume/Start new/Cancel, then "[~] Resuming session"
- State: Same session_id preserved in config

---

## TC-START-005: /start resume in Topic

**Tags:** critical, start, resume
**Preconditions:** Topic with session_id, tmux killed

**Setup:**
```bash
# Get topic's session_id
cat .config.json | jq '.projects["codogram-testing-area"].threads["303"].session_id'
# Kill topic's tmux
tmux kill-session -t claude-codogram-testing-area-test-regular-topic 2>/dev/null || true
```

**Steps:**
```python
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="/start")
# Wait 3s for menu
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
# Press Resume
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Resume")
# Wait 20s
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=303, limit=5)
```

**Expected:**
- UI: Menu with Resume option in topic, then "[~] Resuming session"
- State: Topic's session_id preserved

---

## TC-START-006: /start resume in Branch topic

**Tags:** critical, start, resume, branch
**Preconditions:** Branch topic with session_id, worktree exists, tmux killed

**Setup:**
```bash
# Check branch topic exists
cat .config.json | jq '.projects["codogram-testing-area"].threads["222"]'
# Kill branch's tmux
tmux kill-session -t claude-codogram-testing-area-test-resume 2>/dev/null || true
```

**Steps:**
```python
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=222, text="/start")
# Wait 3s
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
# Press Resume
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Resume")
# Wait 20s
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=222, limit=5)
```

**Expected:**
- UI: "[~] Resuming session", Claude launched in worktree directory
- State: session_id preserved, cwd = worktree_path

---

## TC-START-007: session_id preserved after tmux kill

**Tags:** critical, start, resume
**Preconditions:** Active session with tmux

**Setup:**
```bash
# Get current session_id
BEFORE=$(cat .config.json | jq -r '.projects["codogram-testing-area"].threads["null"].session_id')
echo "Before: $BEFORE"
```

**Steps:**
```bash
# Kill tmux
tmux kill-session -t claude-codogram-testing-area
# Wait 20s for watcher to detect
sleep 20
# Check session_id
AFTER=$(cat .config.json | jq -r '.projects["codogram-testing-area"].threads["null"].session_id')
echo "After: $AFTER"
```

**Expected:**
- UI: "[!] Claude session closed" notification
- State: session_id == BEFORE (not null, not changed)

---

## TC-START-008: /start in forum registers extended menu

**Tags:** critical, start, menu
**Preconditions:** Supergroup with topics enabled

**Steps:**
```python
mcp__telegram__send_message(chat_id=FORUM_CHAT_ID, message="/start")
# Wait 5s
```

**Expected:**
- ASK USER: "Can you see /new_chat and /finish_chat in bot menu?"

---

## TC-START-009: /start in regular group registers basic menu

**Tags:** critical, start, menu
**Preconditions:** Regular group (not forum)

**Steps:**
```python
mcp__telegram__send_message(chat_id=REGULAR_GROUP_ID, message="/start")
# Wait 5s
```

**Expected:**
- ASK USER: "Confirm that /new_chat and /finish_chat are NOT in bot menu"

---

## TC-START-010: Migration updates chat_id

**Tags:** critical, start, migration
**Preconditions:** Bot registered in regular group, active session

**Setup:**
```bash
cat ~/.codogram/config.json | jq '.projects["<project>"].chat_id'
# Note current chat_id
```

**Human action required:**
ASK USER: "Please enable Topics in the test group:
Settings → Topics → Enable. Let me know when done."

**Steps:**
1. After user confirms, wait 5s
2. Check new chat_id:
```bash
cat ~/.codogram/config.json | jq '.projects["<project>"].chat_id'
```
3. Read messages in NEW chat:
```python
mcp__telegram__list_messages(chat_id=NEW_CHAT_ID, limit=5)
```

**Expected:**
- chat_id changed in config
- Notification: "[v] Topics enabled..." in new chat
- ASK USER: "Can you see /new_chat and /finish_chat in bot menu?"

---

## TC-START-011: Permission poller works after migration

**Tags:** critical, start, migration, permissions
**Preconditions:** TC-START-010 completed, Claude running

**Steps:**
```python
mcp__telegram__send_message(chat_id=NEW_CHAT_ID, message="run ls /")
# Wait 10s
mcp__telegram__list_inline_buttons(chat_id=NEW_CHAT_ID)
```

**Expected:**
- Permission prompt with Yes/No buttons in NEW chat

---

## TC-START-012: Watcher works after migration

**Tags:** critical, start, migration, watcher
**Preconditions:** TC-START-010 completed, Claude running

**Steps:**
1. Accept pending permission if any
```python
mcp__telegram__send_message(chat_id=NEW_CHAT_ID, message="read README.md")
# Wait 15s
mcp__telegram__list_messages(chat_id=NEW_CHAT_ID, limit=10)
```

**Expected:**
- Tool call notification (● Read...) in NEW chat

---

## TC-START-013: /start detects stale worktree

**Tags:** critical, start, worktree, recovery
**Preconditions:** Branch topic with worktree_path that doesn't exist

**Setup:**
```bash
# Create branch topic with worktree via /new_chat → Create isolated flow
# Then kill tmux and delete worktree directory
tmux kill-session -t claude-codogram-testing-area-stale-test 2>/dev/null || true
rm -rf /home/superbereza/dev/codogram/.worktrees/stale-test
```

**Steps:**
```python
# Find the topic's thread_id first
mcp__telegram__list_topics(chat_id=-1003356094635, search_query="stale-test")
# Send /start in that topic
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TOPIC_ID, text="/start")
# Wait 3s
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: Warning "[!] Worktree missing" with recovery options
- Buttons: "Recreate worktree", "Create new branch", "Resume in main", "Cancel"

---

## TC-START-014: Stale worktree - Recreate worktree

**Tags:** critical, start, worktree, recovery
**Preconditions:** TC-START-013 setup complete, git branch exists

**Setup:**
```bash
# Ensure branch exists
git branch -l | grep stale-test
```

**Steps:**
```python
# Press "Recreate worktree" button
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Recreate worktree")
# Wait 20s for Claude to launch
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=TOPIC_ID, limit=5)
```

**Expected:**
- UI: Recovery message deleted, Claude launching animation
- State: Worktree recreated at .worktrees/stale-test
- State: Claude session bound to topic

**Verify:**
```bash
ls -la /home/superbereza/dev/codogram/.worktrees/stale-test
```

---

## TC-START-015: Stale worktree - Create new branch

**Tags:** critical, start, worktree, recovery
**Preconditions:** Stale worktree detected, git branch does NOT exist

**Setup:**
```bash
# Delete the git branch
git branch -D stale-test 2>/dev/null || true
# Setup stale worktree state
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TOPIC_ID, text="/start")
# Wait 3s
```

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Create new branch")
# Wait 20s
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=TOPIC_ID, limit=5)
```

**Expected:**
- UI: Recovery message deleted, Claude launching animation
- State: New branch created with worktree
- State: Claude session bound to topic

**Verify:**
```bash
git branch -l | grep stale-test
ls -la /home/superbereza/dev/codogram/.worktrees/stale-test
```

---

## TC-START-016: Stale worktree - Resume in main

**Tags:** critical, start, worktree, recovery
**Preconditions:** Stale worktree detected

**Setup:**
```bash
# Ensure stale worktree state
rm -rf /home/superbereza/dev/codogram/.worktrees/stale-test
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TOPIC_ID, text="/start")
# Wait 3s
```

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Resume in main")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=TOPIC_ID, limit=3)
```

**Expected:**
- UI: "[v] Topic archived. Use General or /new_chat for new session."
- State: Topic closed (archived icon 📁)
- State: No new Claude session started

---

## TC-START-017: Stale worktree - Cancel

**Tags:** smoke, start, worktree, recovery
**Preconditions:** Stale worktree recovery message shown

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Cancel")
# Wait 1s
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=TOPIC_ID, limit=3)
```

**Expected:**
- UI: Recovery message deleted
- State: No changes, topic remains in same state
