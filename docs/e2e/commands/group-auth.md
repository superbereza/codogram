# Group Authorization E2E Tests

Tests for group-based authorization feature. Bot can work in groups if at least one ADMIN_IDS user is a member.

## Prerequisites

- Test group where MCP user is admin/member AND in ADMIN_IDS
- Test group where MCP user is NOT in ADMIN_IDS (or no ADMIN_IDS users present)
- MCP user ID added to ADMIN_IDS in `.env`

---

## TC-GRPAUTH-001: Bot added to group with admin

**Tags:** critical, group-auth
**Preconditions:** MCP user is in ADMIN_IDS, MCP user is member of test group

**Steps:**
```python
# Send any command in group where MCP user is member
mcp__telegram__send_message(chat_id=TEST_GROUP_ID, message="/help")
# Wait 3s
mcp__telegram__list_messages(chat_id=TEST_GROUP_ID, limit=2)
```

**Expected:**
- UI: Bot responds with help message (not blocked)
- State: Group is allowed (admin present)

---

## TC-GRPAUTH-002: Bot added to unauthorized group - one-time message

**Tags:** critical, group-auth
**Preconditions:** Group with no ADMIN_IDS users as members

**Human action required:**
ASK USER: "Please add bot to a group where you are NOT in ADMIN_IDS. Let me know when done."

**Steps:**
```python
# After bot is added, check for rejection message
mcp__telegram__list_messages(chat_id=NO_ADMIN_GROUP_ID, limit=3)
```

**Expected:**
- UI: `[x] Bot not active in this group` (sent once when bot is added)
- State: Group not registered

---

## TC-GRPAUTH-003: Subsequent messages in unauthorized group - silent ignore

**Tags:** critical, group-auth
**Preconditions:** Bot already added to unauthorized group (TC-GRPAUTH-002 completed)

**Steps:**
```python
# Send command in unauthorized group
mcp__telegram__send_message(chat_id=NO_ADMIN_GROUP_ID, message="/help")
# Wait 3s
mcp__telegram__list_messages(chat_id=NO_ADMIN_GROUP_ID, limit=3)
```

**Expected:**
- UI: No new message from bot (silent ignore, no spam)
- State: Command not processed

---

## TC-GRPAUTH-004: Admin leaves group - bot deactivated

**Tags:** critical, group-auth
**Preconditions:**
- Bot in group with MCP user as only ADMIN_IDS member
- Another non-admin user in group to send commands

**Steps:**
1. MCP user leaves the group (or is removed by another admin)
2. Non-admin user sends `/help` in group

**Expected:**
- UI: `[!] Admin left. Bot deactivated` sent to group
- State: Group no longer active, subsequent commands blocked

**Note:** This test requires manual observation or a second test account.

---

## TC-GRPAUTH-005: Private chat still works for admins

**Tags:** smoke, group-auth
**Preconditions:** MCP user is in ADMIN_IDS

**Steps:**
```python
# Send command in private chat (direct message to bot)
mcp__telegram__send_message(chat_id=BOT_PRIVATE_CHAT_ID, message="/help")
# Wait 3s
mcp__telegram__list_messages(chat_id=BOT_PRIVATE_CHAT_ID, limit=2)
```

**Expected:**
- UI: Normal help response
- State: Private chat unaffected by group auth

---

## TC-GRPAUTH-006: Private chat blocked for non-admins

**Tags:** critical, group-auth
**Preconditions:** User NOT in ADMIN_IDS sends message in private chat

**Steps:**
```python
# Non-admin sends command in private chat
# (Requires second test account not in ADMIN_IDS)
```

**Expected:**
- UI: `[x] Not admin. Your ID: <user_id>`
- State: Command not processed

**Note:** This test requires a second Telegram account not in ADMIN_IDS.

---

## TC-GRPAUTH-007: Button callback blocked in unauthorized group

**Tags:** full, group-auth
**Preconditions:** Group with no ADMIN_IDS members, message with inline buttons exists

**Steps:**
```python
# Attempt to press inline button in unauthorized group
mcp__telegram__press_inline_button(chat_id=NO_ADMIN_GROUP_ID, button_text="Some Button")
```

**Expected:**
- UI: Callback popup shows `[x] Bot not active in this group`
- State: Button action not processed

---

## TC-GRPAUTH-008: Multiple admins - one leaves, bot still works

**Tags:** full, group-auth
**Preconditions:**
- Bot in group with two ADMIN_IDS users as members
- Both users have their IDs in ADMIN_IDS

**Steps:**
1. First admin leaves the group
2. Send `/help` in group

**Expected:**
- UI: Normal help response (second admin still present)
- State: Group remains active

---

## TC-GRPAUTH-009: Admin rejoins group - bot reactivated

**Tags:** full, group-auth
**Preconditions:**
- Group was deactivated (no ADMIN_IDS members)
- Admin rejoins group

**Steps:**
1. Admin (ADMIN_IDS user) joins the group
2. Send `/help` in group

**Expected:**
- UI: Normal help response
- State: Group is active again (admin present)
