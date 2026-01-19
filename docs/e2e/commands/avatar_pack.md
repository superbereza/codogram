# Avatar Emoji Pack Tests

Emoji pack from member avatars for topic icons.

## TC-AVATAR-001: /exp_avatar_pack shows create prompt when OFF

**Tags:** critical, avatar_pack
**Preconditions:** Project registered, feat_avatar_pack=false

**Setup:**
```bash
# Ensure pack is disabled
cat ~/.codogram/config.json | jq '.projects["codogram-testing-area"].feat_avatar_pack'
# Should be false or missing
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/exp_avatar_pack")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: `[?] Create avatar pack?` with description
- Buttons: "Yes, create" and "Not now"
- State: feat_avatar_pack still false

---

## TC-AVATAR-002: Create avatar pack via button

**Tags:** critical, avatar_pack
**Preconditions:** TC-AVATAR-001 passed, create prompt visible

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Yes, create")
# Wait 5s (pack creation takes time)
mcp__telegram__list_messages(chat_id=-1003356094635, limit=3)
```

**Expected:**
- UI: First `[~] Creating avatar pack...`, then `[v] Gift unlocked` with pack link
- State:
  - `feat_avatar_pack: true` in config
  - `emoji_pack_name` set in config
  - `emoji_map` has entries for admins

**Verify:**
```bash
cat ~/.codogram/config.json | jq '.projects["codogram-testing-area"] | {feat_avatar_pack, emoji_pack_name, emoji_map}'
```

---

## TC-AVATAR-003: /exp_avatar_pack shows disable prompt when ON

**Tags:** critical, avatar_pack
**Preconditions:** Pack created (TC-AVATAR-002)

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/exp_avatar_pack")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
mcp__telegram__list_inline_buttons(chat_id=-1003356094635)
```

**Expected:**
- UI: `[?] Disable avatar pack?` with warning about deletion
- Buttons: "Yes, disable" and "Keep it"
- State: feat_avatar_pack still true

---

## TC-AVATAR-004: Cancel keeps pack enabled

**Tags:** full, avatar_pack
**Preconditions:** TC-AVATAR-003 passed, disable prompt visible

**Steps:**
```python
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Keep it")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: "Cancelled"
- State: feat_avatar_pack still true, pack still exists

---

## TC-AVATAR-005: Disable avatar pack via button

**Tags:** critical, avatar_pack
**Preconditions:** Pack enabled

**Setup:**
```bash
# Note pack name before deletion
cat ~/.codogram/config.json | jq '.projects["codogram-testing-area"].emoji_pack_name'
```

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/exp_avatar_pack")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Yes, disable")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=3)
```

**Expected:**
- UI: `[v] Avatar pack disabled`
- State:
  - `feat_avatar_pack: false`
  - `emoji_pack_name: null`
  - `emoji_map: {}`

**Verify:**
```bash
cat ~/.codogram/config.json | jq '.projects["codogram-testing-area"] | {feat_avatar_pack, emoji_pack_name, emoji_map}'
```

---

## TC-AVATAR-006: /settings shows avatar_pack status

**Tags:** critical, avatar_pack, settings
**Preconditions:** Project registered

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/settings")
# Wait 3s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: Contains `• /exp_avatar_pack: ○ off` or `• /exp_avatar_pack: ● on`
- State: Matches config value

---

## TC-AVATAR-007: Topic launch shows emoji hint when pack enabled

**Tags:** critical, avatar_pack, new_chat
**Preconditions:** Pack enabled (feat_avatar_pack=true)

**Setup:**
```bash
# Enable pack first if not enabled
# ... or use TC-AVATAR-002
```

**Steps:**
```python
# Create topic via /new_chat → Create here → send name
mcp__telegram__send_message(chat_id=-1003356094635, message="/new_chat")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Create here")
# Wait 2s
mcp__telegram__send_message(chat_id=-1003356094635, message="avatar_test")
# Wait 10s (Claude launch)
# Find the new topic and read messages
mcp__telegram__list_topics(chat_id=-1003356094635)
# Get topic_id, then:
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=TOPIC_ID, limit=5)
```

**Expected:**
- UI: Launch message contains `→ Check this pack...` with link to emoji pack
- State: Thread created, pack link valid

**Cleanup:**
```python
# Archive topic via /finish_chat
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TOPIC_ID, text="/finish_chat")
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Archive")
```

---

## TC-AVATAR-008: Topic launch has NO hint when pack disabled

**Tags:** full, avatar_pack, new_chat
**Preconditions:** Pack disabled (feat_avatar_pack=false)

**Steps:**
```python
# Create topic via /new_chat → Create here → send name
mcp__telegram__send_message(chat_id=-1003356094635, message="/new_chat")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Create here")
# Wait 2s
mcp__telegram__send_message(chat_id=-1003356094635, message="no_hint_test")
# Wait 10s
mcp__telegram__list_topics(chat_id=-1003356094635)
mcp__telegram__list_messages(chat_id=-1003356094635, reply_to=TOPIC_ID, limit=5)
```

**Expected:**
- UI: Launch message does NOT contain `→ Check this pack...`
- State: Thread created normally

**Cleanup:**
```python
# Archive topic via /finish_chat
mcp__telegram__reply_to_message(chat_id=-1003356094635, message_id=TOPIC_ID, text="/finish_chat")
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Archive")
```

---

## TC-AVATAR-009: Member join adds to pack (ASK USER)

**Tags:** full, avatar_pack, members
**Preconditions:** Pack enabled, test user not in pack

**Steps:**
1. Enable pack: `/exp_avatar_pack` → "Yes, create"
2. **ASK USER:** "Please add a test user to the group"
3. Wait 5s
4. Check config:
```bash
cat ~/.codogram/config.json | jq '.projects["codogram-testing-area"].emoji_map'
```

**Expected:**
- State: New user_id appears in emoji_map with custom_emoji_id
- **ASK USER:** "Does the emoji_map now have an entry for the new user?"

---

## TC-AVATAR-010: Member leave removes from pack (ASK USER)

**Tags:** full, avatar_pack, members
**Preconditions:** Pack enabled, test user in pack (from TC-AVATAR-009)

**Steps:**
1. Note user's emoji_id in config
2. **ASK USER:** "Please remove the test user from the group"
3. Wait 5s
4. Check config:
```bash
cat ~/.codogram/config.json | jq '.projects["codogram-testing-area"].emoji_map'
```

**Expected:**
- State: User's entry removed from emoji_map
- **ASK USER:** "Is the user's emoji_id gone from emoji_map?"

---

## TC-AVATAR-011: "Not now" cancels create

**Tags:** full, avatar_pack
**Preconditions:** Pack disabled, create prompt visible

**Steps:**
```python
mcp__telegram__send_message(chat_id=-1003356094635, message="/exp_avatar_pack")
# Wait 2s
mcp__telegram__press_inline_button(chat_id=-1003356094635, button_text="Not now")
# Wait 2s
mcp__telegram__list_messages(chat_id=-1003356094635, limit=2)
```

**Expected:**
- UI: "Cancelled"
- State: feat_avatar_pack still false

---

## TC-AVATAR-012: Pack link is valid (ASK USER)

**Tags:** full, avatar_pack
**Preconditions:** Pack created

**Steps:**
1. Get pack link from config:
```bash
cat ~/.codogram/config.json | jq -r '.projects["codogram-testing-area"].emoji_pack_name'
# Link: t.me/addemoji/{pack_name}
```
2. **ASK USER:** "Open link t.me/addemoji/{pack_name} in Telegram. Does it show the emoji pack with avatar stickers?"

**Expected:**
- **ASK USER confirms:** Pack opens with circular avatar emojis
