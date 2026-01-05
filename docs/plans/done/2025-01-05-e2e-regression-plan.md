# E2E Regression Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Execute full E2E regression test suite for refactor-bot branch to verify all functionality works after TelegramQueue migration.

**Architecture:** 3-stage testing (Smoke → Critical → Full) using Telegram MCP for automated interaction. Each test sends commands, reads responses, verifies expected behavior. Tests run in chat -1003356094635.

**Tech Stack:** Telegram MCP, tmux, Claude Code, pytest (for unit test verification)

**Design doc:** `docs/tests/2025-01-05-e2e-regression.md`

---

### Task 1: Setup Test Environment

**Files:**
- Verify: `/home/superbereza/dev/codogram/.worktrees/refactor-bot/restart.sh`
- Check: `.config.json`

**Step 1: Verify bot running from worktree**

Run: `ps aux | grep codogram | grep -v grep`
Expected: Process running from `.worktrees/refactor-bot`

If not running:
```bash
cd /home/superbereza/dev/codogram/.worktrees/refactor-bot && ./restart.sh
```

**Step 2: Create test tmux session**

```bash
tmux kill-session -t claude-codogram-testing-area 2>/dev/null || true
tmux new-session -d -s claude-codogram-testing-area -c /home/superbereza/dev/codogram/.worktrees/refactor-bot
tmux send-keys -t claude-codogram-testing-area "claude" Enter
```

**Step 3: Verify tmux exists**

Run: `tmux has-session -t =claude-codogram-testing-area && echo "OK"`
Expected: OK

**Step 4: Wait for Claude to initialize**

Run: `sleep 10 && tmux capture-pane -t claude-codogram-testing-area -p | tail -5`
Expected: Claude prompt visible (❯ or similar)

---

### Task 2: Smoke Test S1-S3 (Basic Commands)

**Step 1: Test S1 - /help**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/help")
```

Wait 2s, then:
```python
mcp__telegram__get_messages(chat_id=-1003356094635, page_size=2)
```

Expected: Response contains "Commands" and lists /start, /new, /restart, etc.

**Step 2: Test S2 - /settings**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
```

Wait 2s, then read response.
Expected: Shows "Settings" with project name and "Auto-accept: OFF" or "⚡ ON"

**Step 3: Test S3 - /get_debug_ids**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/get_debug_ids")
```

Expected: Shows "Your user ID:", "This chat ID: -1003356094635", "Thread ID:"

**Step 4: Update test document with results**

Edit `docs/tests/2025-01-05-e2e-regression.md`:
- Mark S1, S2, S3 status as ✅ or ❌

---

### Task 3: Smoke Test S4-S5 (/start Connection)

**Step 1: Test S4 - /start in General (tmux exists)**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/start")
```

Expected: "Connected to claude-codogram-testing-area" or similar success message

**Step 2: Verify config updated**

```bash
cat /home/superbereza/dev/codogram/.config.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
p = d['projects'].get('codogram-testing-area', {})
print(f'chat_id: {p.get(\"chat_id\")}')
print(f'threads: {list(p.get(\"threads\", {}).keys())}')
"
```

Expected: chat_id = -1003356094635, threads contains "null"

**Step 3: Update test document**

Mark S4 status. S5 (Topic) requires forum - skip if not available or test manually.

---

### Task 4: Smoke Test S6 (Message Routing)

**Step 1: Send test message**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="E2E test message routing")
```

**Step 2: Verify message in tmux**

```bash
tmux capture-pane -t claude-codogram-testing-area -p | grep -i "E2E test"
```

Expected: Message visible in tmux pane

**Step 3: Check logs for routing**

```bash
tail -20 /home/superbereza/dev/codogram/logs/codogram.log | grep -i "routing\|tmux_send"
```

Expected: Log shows message routed to correct tmux

**Step 4: Update test document**

Mark S6 status.

---

### Task 5: Smoke Test S7-S8 (Permission & Auto-accept)

**Step 1: Check current auto_accept status**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
```

Note current status (ON/OFF).

**Step 2: Test S8 - Toggle auto_accept**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/auto_accept")
```

Expected: Shows new status (toggled from previous)

**Step 3: Verify dynamic effect in logs**

If a permission prompt occurs in tmux, check logs:
```bash
tail -50 /home/superbereza/dev/codogram/logs/codogram.log | grep -i "auto_accept"
```

Expected: If auto_accept ON and permission appeared, log shows "auto_accept ... option=N"

**Step 4: Test S7 - Permission buttons**

This requires Claude to request permission. If one appears:
```python
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

Expected: Shows buttons like "1. Yes", "2. No" etc.

**Step 5: Update test document**

Mark S7, S8 status.

---

### Task 6: Critical Test C1 (tmux Exact Match)

**Step 1: List all tmux sessions**

```bash
tmux list-sessions
```

Expected: Shows `claude-codogram-testing-area` and possibly others like `claude-codogram-immortal`

**Step 2: Verify exact match logic**

```bash
# This should FAIL (no exact match)
tmux has-session -t =claude-codogram-testing && echo "FOUND" || echo "NOT FOUND"

# This should SUCCEED (exact match)
tmux has-session -t =claude-codogram-testing-area && echo "FOUND" || echo "NOT FOUND"
```

Expected: First = NOT FOUND, Second = FOUND

**Step 3: Verify in bot code**

```bash
grep -n "has-session.*=" /home/superbereza/dev/codogram/.worktrees/refactor-bot/src/codogram/tmux.py
```

Expected: Shows `has-session -t f"={self.name}"`

**Step 4: Update test document**

Mark C1 status.

---

### Task 7: Critical Test C2-C4 (Isolation)

**Step 1: Test C2 - Poller isolation**

Check logs for poller messages:
```bash
grep "poller\|Thread poller" /home/superbereza/dev/codogram/logs/codogram.log | tail -20
```

Verify each poller sends only to its own thread_id.

**Step 2: Test C4 - auto_accept isolation**

```bash
cat /home/superbereza/dev/codogram/.config.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
for pname, p in d['projects'].items():
    print(f'{pname}: project.auto_accept={p.get(\"auto_accept\")}')
    for tid, t in p.get('threads', {}).items():
        print(f'  thread {tid}: auto_accept={t.get(\"auto_accept\", False)}')
"
```

Expected: Different threads can have different auto_accept values.

**Step 3: Update test document**

Mark C2, C3, C4 status. C3 (session isolation) requires multi-thread setup - note if skipped.

---

### Task 8: Critical Test C5-C8 (/start Scenarios)

**Step 1: Test C7 - /start in General uses correct tmux**

Check logs after /start:
```bash
grep "start\|tmux\|thread" /home/superbereza/dev/codogram/logs/codogram.log | tail -30
```

Verify General uses `claude-{project}` naming, not CWD discovery.

**Step 2: Document other scenarios**

C5 (dir not exists), C6 (tmux not exists), C8 (new topic) require specific setup.
Note in test document which were tested vs skipped.

**Step 3: Update test document**

Mark C5-C8 status.

---

### Task 9: Critical Test C9-C12 (Session Management)

**Step 1: Test C9 - /new**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/new")
```

Expected: Response about new session, config shows awaiting_new_session=true

**Step 2: Test C10 - /restart**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/restart")
```

Expected: Confirmation prompt with buttons

**Step 3: Check session binding config**

```bash
cat /home/superbereza/dev/codogram/.config.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
for pname, p in d['projects'].items():
    for tid, t in p.get('threads', {}).items():
        if t.get('start_requested_at'):
            print(f'{pname}/{tid}: start_requested_at={t.get(\"start_requested_at\")}')
"
```

Expected: Shows timestamps for threads that ran /start

**Step 4: Update test document**

Mark C9-C12 status.

---

### Task 10: Critical Test C13-C15 (History Watcher)

**Step 1: Trigger tool call in Claude**

In tmux, make Claude use a tool (e.g., send a message that triggers Read or Bash).

**Step 2: Verify tool output in Telegram**

```python
mcp__telegram__get_messages(chat_id=-1003356094635, page_size=10)
```

Expected: Tool call output visible (with ● prefix or similar formatting)

**Step 3: Test C15 - Long output chunking**

If tool output was long, verify multiple messages received.

**Step 4: Update test document**

Mark C13-C15 status.

---

### Task 11: Run Unit Tests

**Step 1: Run all unit tests**

```bash
cd /home/superbereza/dev/codogram/.worktrees/refactor-bot
PYTHONPATH=src pytest tests/ -v --tb=short 2>&1 | tail -50
```

Expected: All tests PASS

**Step 2: Document any failures**

If failures, note them for investigation.

---

### Task 12: Final Summary

**Step 1: Review test document**

Read `docs/tests/2025-01-05-e2e-regression.md` and count:
- Total tests attempted
- Passed (✅)
- Failed (❌)
- Skipped (⏭️)

**Step 2: Create summary**

Add summary section to test document:

```markdown
## Results Summary

**Date:** YYYY-MM-DD HH:MM
**Tester:** Claude via MCP

### Этап 1 - Smoke
- S1: ✅/❌
- S2: ✅/❌
...

### Этап 2 - Critical
- C1: ✅/❌
...

### Overall
- Passed: X/Y
- Failed: Z
- Skipped: W

### Issues Found
1. [Issue description]
```

**Step 3: Commit test results**

```bash
git add docs/tests/2025-01-05-e2e-regression.md
git commit -m "test: E2E regression results for refactor-bot"
```

---

---

### Task 13: Full Test F1-F3 (Thread Management)

**Step 1: Test F1 - /thread_create**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/thread_create testthread")
```

Expected: Creates topic, shows confirmation, config has new thread entry

**Step 2: Verify thread in config**

```bash
cat /home/superbereza/dev/codogram/.config.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
for pname, p in d['projects'].items():
    for tid, t in p.get('threads', {}).items():
        if 'testthread' in t.get('name', ''):
            print(f'Found: {pname}/{tid} = {t}')
"
```

**Step 3: Test F2 - /thread_delete**

Requires being in the topic. If MCP can reply to topic:
```python
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TOPIC_MSG_ID, text="/thread_delete")
```

Expected: Confirmation prompt, then deletes topic + config

**Step 4: Test F3 - /start in pending thread**

Create a pending thread (topic without full config), then /start.
Expected: Upgrades to full thread with tmux naming.

**Step 5: Update test document**

Mark F1-F3 status.

---

### Task 14: Full Test F4-F5 (Branch/Worktree)

**Step 1: Test F4 - /branch_create**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/branch_create e2e-test-branch")
```

Expected: Shows base branch selection, creates worktree + topic

**Step 2: Verify worktree created**

```bash
git -C /home/superbereza/dev/codogram worktree list | grep e2e-test
```

**Step 3: Test F5 - /branch_finish**

In the branch topic:
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/branch_finish")
```

Expected: Merge options, cleanup worktree + topic

**Step 4: Update test document**

Mark F4-F5 status.

---

### Task 15: Full Test F6-F9 (/start Edge Cases)

**Step 1: Test F6 - Multiple tmux in cwd**

Create second tmux:
```bash
tmux new-session -d -s claude-codogram-testing-area-extra -c /home/superbereza/dev/codogram/.worktrees/refactor-bot
```

Then /start - should show selection.

**Step 2: Test F7 - custom_path flow**

Trigger by /start when dir doesn't exist, select "Custom path" button.

**Step 3: Test F8 - git_clone flow**

Trigger by /start, select clone option, enter URL.

**Step 4: Test F9 - /start in unregistered topic**

Create topic manually in Telegram, then /start there.
Expected: Registers thread + launches.

**Step 5: Cleanup extra tmux**

```bash
tmux kill-session -t claude-codogram-testing-area-extra 2>/dev/null || true
```

**Step 6: Update test document**

Mark F6-F9 status.

---

### Task 16: Full Test F10-F12 (Session Commands)

**Step 1: Test F10 - /clear**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/clear")
```

Expected: Clears session, sets awaiting_new_session

**Step 2: Test F11 - /esc**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/esc")
```

Expected: Sends Escape to tmux

Verify:
```bash
# Check logs for esc send
tail -10 /home/superbereza/dev/codogram/logs/codogram.log | grep -i esc
```

**Step 3: Test F12 - /resume**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/resume")
```

Expected: Shows resume options or error if no sessions

**Step 4: Update test document**

Mark F10-F12 status.

---

### Task 17: Full Test F13-F15 (Error Handling)

**Step 1: Test F13 - tmux died**

```bash
# Kill Claude process in tmux (not the tmux itself)
tmux send-keys -t claude-codogram-testing-area C-c
tmux send-keys -t claude-codogram-testing-area "exit" Enter
```

Wait for poller to detect crash.

Expected: "Claude crashed" notification in Telegram

**Step 2: Test F14 - /start with missing cwd**

Create project with invalid cwd, then /start.
Expected: Graceful error message

**Step 3: Test F15 - /settings without project**

In a new chat without project:
Expected: "No project. Use /start first."

(Already tested in S2 if project didn't exist)

**Step 4: Restore test tmux**

```bash
tmux new-session -d -s claude-codogram-testing-area -c /home/superbereza/dev/codogram/.worktrees/refactor-bot
tmux send-keys -t claude-codogram-testing-area "claude" Enter
```

**Step 5: Update test document**

Mark F13-F15 status.

---

### Task 18: Full Test F16-F17 (Bot Lifecycle)

**Step 1: Test F16 - Bot restart recovery**

```bash
# Note current poller/watcher state
tail -5 /home/superbereza/dev/codogram/logs/codogram.log

# Restart bot
cd /home/superbereza/dev/codogram/.worktrees/refactor-bot && ./restart.sh

# Wait for restore
sleep 5

# Check restore logs
grep -i "restore\|project_restored" /home/superbereza/dev/codogram/logs/codogram.log | tail -10
```

Expected: Logs show projects restored, pollers/watchers restarted

**Step 2: Test F17 - Config persistence**

```python
# Toggle auto_accept
mcp__telegram__send_message(chat_id=-1003356094635, message="/auto_accept")
```

Note the new value.

```bash
# Restart bot
cd /home/superbereza/dev/codogram/.worktrees/refactor-bot && ./restart.sh
sleep 3
```

```python
# Check value preserved
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
```

Expected: auto_accept value same as before restart

**Step 3: Update test document**

Mark F16-F17 status.

---

### Task 19: Full Test F18-F20 (Callbacks)

**Step 1: Test F18 - cancel button**

Trigger a flow with cancel button (e.g., /restart):
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/restart")
```

Then press cancel:
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Cancel")
```

Expected: Flow cancelled, message updated

**Step 2: Test F19 - restart:confirm**

```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/restart")
```

```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Confirm")
```

Expected: Claude restarted

**Step 3: Test F20 - select_tmux**

Create multiple tmux, /start, then select one.
(May have been tested in F6)

**Step 4: Update test document**

Mark F18-F20 status.

---

### Task 20: Final Summary (Updated)

**Step 1: Review all test results**

Read `docs/tests/2025-01-05-e2e-regression.md` and count all 43 tests:
- Этап 1 (Smoke): S1-S8
- Этап 2 (Critical): C1-C15
- Этап 3 (Full): F1-F20

**Step 2: Create comprehensive summary**

```markdown
## Results Summary

**Date:** YYYY-MM-DD HH:MM
**Branch:** refactor-bot
**Tester:** Claude via MCP

### Этап 1 - Smoke (8 tests)
| ID | Test | Status |
|----|------|--------|
| S1 | /help | |
| S2 | /settings | |
| S3 | /get_debug_ids | |
| S4 | /start General | |
| S5 | /start Topic | |
| S6 | Message routing | |
| S7 | Permission buttons | |
| S8 | Auto-accept dynamic | |

### Этап 2 - Critical (15 tests)
| ID | Test | Status |
|----|------|--------|
| C1 | tmux exact match | |
| C2 | Poller isolation | |
| C3 | Session isolation | |
| C4 | auto_accept isolation | |
| C5 | /start dir not exists | |
| C6 | /start tmux not exists | |
| C7 | /start General naming | |
| C8 | /start Topic naming | |
| C9 | /new | |
| C10 | /restart | |
| C11 | Session binding | |
| C12 | start_requested_at | |
| C13 | Tool call display | |
| C14 | Watcher isolation | |
| C15 | Long output chunking | |

### Этап 3 - Full (20 tests)
| ID | Test | Status |
|----|------|--------|
| F1 | /thread_create | |
| F2 | /thread_delete | |
| F3 | /start pending | |
| F4 | /branch_create | |
| F5 | /branch_finish | |
| F6 | Multiple tmux select | |
| F7 | custom_path flow | |
| F8 | git_clone flow | |
| F9 | /start unregistered topic | |
| F10 | /clear | |
| F11 | /esc | |
| F12 | /resume | |
| F13 | tmux died | |
| F14 | missing cwd | |
| F15 | no project | |
| F16 | Bot restart recovery | |
| F17 | Config persistence | |
| F18 | cancel button | |
| F19 | restart:confirm | |
| F20 | select_tmux | |

### Overall
- **Total:** 43
- **Passed:** X
- **Failed:** Y
- **Skipped:** Z

### Issues Found
1. [Description]
```

**Step 3: Commit test results**

```bash
git add docs/tests/2025-01-05-e2e-regression.md docs/plans/2025-01-05-e2e-regression-plan.md
git commit -m "test: complete E2E regression for refactor-bot (X/43 passed)"
```

---

## Execution Notes

- Tasks 1: Setup environment
- Tasks 2-10: Smoke + Critical tests (Этапы 1-2)
- Tasks 13-19: Full coverage tests (Этап 3)
- Task 11: Unit tests verification
- Tasks 12, 20: Summary & commit
- Some tests require forum group with topics
- Some tests require manual intervention (topic creation, permission prompts)
