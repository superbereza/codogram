# History Watcher Tests

Tool call output delivery to Telegram.

## TC-WATCHER-001: Tool call appears in correct topic

**Tags:** smoke, critical, watcher
**Preconditions:** Active session in topic, Claude running

**Setup:**
```bash
# Ensure session bound to topic
cat .config.json | jq '.projects["codogram-testing-area"].threads["303"]'
```

**Steps:**
```python
# Send message that triggers tool call (e.g., ask to read a file)
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Read /tmp/test.txt")
# Wait 30s for Claude to process
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=303, limit=10)
```

**Expected:**
- UI: Tool call output appears in topic 303 (contains file content or error)
- State: Watcher task running for this thread

---

## TC-WATCHER-002: Tool call NOT in other topics (isolation)

**Tags:** critical, watcher, isolation
**Preconditions:** Two active topics with different sessions

**Setup:**
```bash
# Ensure two topics exist with sessions
# Topic A: 303 (test-regular-topic)
# Topic B: 222 (test-resume)
cat .config.json | jq '.projects["codogram-testing-area"].threads | keys'
```

**Steps:**
```python
# Send message to Topic A
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=303, text="Echo test isolation")
# Wait 30s
# Check Topic B - should NOT have the output
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=222, limit=5)
# Check Topic A - SHOULD have the output
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=303, limit=5)
```

**Expected:**
- UI: Output ONLY in Topic A (303), NOT in Topic B (222)
- State: Each topic has independent watcher

---

## TC-WATCHER-003: Long tool output chunking

**Tags:** full, watcher
**Preconditions:** Active session

**Steps:**
```python
# Ask Claude to output something long (>4096 chars)
mcp__telegram__send_message(chat_id=-1003356094635, message="List all files in /usr recursively, first 200 lines")
# Wait 60s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=10)
```

**Expected:**
- UI: Multiple messages if output > 4096 chars
- State: All chunks delivered in order

---

## TC-WATCHER-004: Watcher starts for resumed session

**Tags:** critical, watcher, resume
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
# Wait 30s for Claude to start and bind

# 2. Send message that triggers tool call
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TEST_TOPIC, text="List files in current directory")
# Wait 30s

# 3. Check for tool call output
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=TEST_TOPIC, limit=10)
```

**Expected:**
- UI: Tool call output appears in topic (e.g., "Read" tool or file listing)
- State: `thread.watcher_task` is not None and not done
- Note: This test verifies fix for bug where watcher didn't start on resume

---

## TC-WATCHER-005: Watcher output after bot restart

**Tags:** full, watcher, lifecycle
**Preconditions:** Running session, bot about to restart

**Setup:**
```bash
# Ensure active session
tmux has-session -t claude-codogram-testing-area-main
```

**Steps:**
```bash
# 1. Restart bot
./stop-and-restart.sh

# Wait 5s for bot to start
```

```python
# 2. Send message that triggers tool call
mcp__telegram__send_message(chat_id=-1003356094635, message="Echo test after restart")
# Wait 30s

# 3. Check for output
mcp__telegram__list_messages(chat_id=-1003356094635, limit=10)
```

**Expected:**
- UI: Tool call output appears after bot restart
- State: Watcher restarted by first user message

---

## TC-WATCHER-006: Tool call truncated in short mode (verbose=off)

**Tags:** full, watcher, verbose
**Preconditions:** verbose=off (default), active session

**Setup:**
```python
# Ensure verbose is off
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 2s - verify "verbose: ○ off"
```

**Steps:**
```python
# Trigger tool call with long output (e.g., Bash with multiline command)
mcp__telegram__send_message(chat_id=-1003356094635, message="Run: for i in {1..20}; do echo line$i; done")
# Wait 30s for tool call to appear
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: Tool call body shows max 5 lines + `[truncated]` indicator
- State: verbose=false in config

---

## TC-WATCHER-007: Tool call full in verbose mode (verbose=on)

**Tags:** full, watcher, verbose
**Preconditions:** verbose=on enabled, active session

**Setup:**
```python
# Enable verbose
mcp__telegram__send_message(chat_id=-1003356094635, message="/verbose")
# Wait 2s - verify "Verbose output: ● on"
```

**Steps:**
```python
# Trigger tool call with long output
mcp__telegram__send_message(chat_id=-1003356094635, message="Run: for i in {1..20}; do echo line$i; done")
# Wait 30s for tool call to appear
mcp__telegram__list_messages(chat_id=-1003356094635, limit=5)
```

**Expected:**
- UI: Tool call body shows ALL lines (no truncation, no `[truncated]`)
- State: verbose=true in config

**Cleanup:**
```python
# Disable verbose
mcp__telegram__send_message(chat_id=-1003356094635, message="/verbose")
```
