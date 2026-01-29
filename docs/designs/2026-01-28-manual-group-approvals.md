# Manual Group Approvals with Tracking

## Problem

Currently when a group is manually approved by bot admin (via "Approve" button), it gets invalidated on revalidation if the approving admin is not a group admin. The `revalidate()` function checks `_has_our_admin()` which returns False because the bot admin may not be an admin OF that specific group.

## Solution

Track manually approved groups separately with metadata about who approved them. Different validation rules apply:

- **Auto-approved groups**: Bot admin is a group admin → use existing `_has_our_admin()` logic
- **Manually approved groups**: Track approver → invalidate only if approver leaves the group

## Data Model

### Before (config.json)
```json
{
  "allowed_groups": [-1001234567890, -1009876543210]
}
```

### After
```json
{
  "allowed_groups": [-1001234567890],
  "manual_approvals": {
    "-1009876543210": {
      "approved_by": 34185809,
      "approved_at": "2026-01-28T12:00:00Z",
      "grace_until": null
    }
  }
}
```

**Fields:**
- `approved_by` - user_id of bot admin who clicked Approve
- `approved_at` - timestamp for audit trail and monthly review
- `grace_until` - set when approving admin leaves, group invalidated after this time

## Validation Rules

### Auto-approved groups (existing)
- Must have at least one ADMIN_IDS member as group administrator
- Revalidated on bot restart via `_has_our_admin()`

### Manually approved groups (new)
1. Valid if `grace_until` is None or in future
2. Check if approving admin is still in group (not "left" or "kicked")
3. If approver left: start 24h grace period, notify bot admin
4. Monthly review: 30 days after approval, send reminder with [Keep]/[Revoke] buttons

## Approval Flow

### Current
1. Unauthorized group sends message
2. Bot admin receives alert with [Approve]/[Dismiss] buttons
3. Admin clicks Approve → `add_allowed_group(chat_id)`
4. Group added to `allowed_groups` list

### New
1. Unauthorized group sends message
2. Bot admin receives alert with [Approve]/[Dismiss] buttons
3. Admin clicks Approve → `add_manual_approval(chat_id, approved_by=user_id)`
4. Group added to `manual_approvals` dict with metadata
5. Monthly review scheduled

## Revalidation Logic

```python
async def revalidate(self, bot, chat_id: int) -> bool:
    # Auto-approved: existing logic
    if chat_id in get_allowed_groups():
        return await self._has_our_admin(bot, chat_id)

    # Manual approval
    approval = get_manual_approval(chat_id)
    if not approval:
        return False

    # Check grace period expired
    if approval.get("grace_until"):
        if datetime.now(UTC) > datetime.fromisoformat(approval["grace_until"]):
            remove_manual_approval(chat_id)
            return False
        return True  # Still in grace period

    # Check approver still in group
    try:
        member = await bot.get_chat_member(chat_id, approval["approved_by"])
        if member.status in ("left", "kicked"):
            start_grace_period(chat_id, hours=24)
            await self._notify_approver_left(bot, chat_id)
            return True  # Valid during grace
    except Exception:
        pass  # Can't check, assume valid

    # Monthly review check
    approved_at = datetime.fromisoformat(approval["approved_at"])
    if datetime.now(UTC) - approved_at > timedelta(days=30):
        await self._notify_monthly_review(bot, chat_id)

    return True
```

## New Command: /allowed_groups

Shows all manually approved groups with management options.

**Output:**
```
📋 Manually approved groups:

1. Test Chat (-1001234567890)
   Approved: 2026-01-15 by you
   [Revoke]

2. Dev Group (-1009876543210)
   ⚠️ Grace period until 2026-01-29 12:00
   Approver left group
   [Keep] [Revoke]
```

**Callbacks:**
- `mangrp:revoke:{chat_id}` - Remove from manual_approvals
- `mangrp:keep:{chat_id}` - Clear grace_until, reset approved_at for fresh 30 days

## New Strings

```python
# Notifications
ADMIN_APPROVER_LEFT = """`[!]` Approving admin left group

Group: {chat_title}
Chat ID: `{chat_id}`

Access will be revoked in 24h unless re\\-approved\\."""

ADMIN_MONTHLY_REVIEW = """`[i]` Monthly review for group

Group: {chat_title}
Chat ID: `{chat_id}`
Approved: {approved_at}"""

BTN_KEEP_GROUP = "✓ Keep"
BTN_REVOKE_GROUP = "✗ Revoke"

# /allowed_groups command
ALLOWED_GROUPS_HEADER = "`[i]` Manually approved groups:"
ALLOWED_GROUPS_EMPTY = "`[i]` No manually approved groups"
ALLOWED_GROUPS_ITEM = """{index}\\. {chat_title} \\(`{chat_id}`\\)
   Approved: {approved_at}"""
ALLOWED_GROUPS_GRACE = """   ⚠️ Grace period until {grace_until}
   Approver left group"""

GROUP_ACCESS_REVOKED = "`[x]` Bot access has been revoked"
```

## Files to Modify

1. **config.py**
   - Add `get_manual_approval(chat_id)`
   - Add `get_all_manual_approvals()`
   - Add `add_manual_approval(chat_id, approved_by)`
   - Add `remove_manual_approval(chat_id)`
   - Add `start_grace_period(chat_id, hours)`
   - Add `clear_grace_period(chat_id)`
   - Modify `is_group_allowed()` to check both sources

2. **services/group_auth.py**
   - Modify `revalidate()` to handle manual approvals differently
   - Add `_notify_approver_left()`
   - Add `_notify_monthly_review()`

3. **handlers/group_admin.py**
   - Change `add_allowed_group()` to `add_manual_approval()` in approve handler

4. **handlers/settings.py** (or new handlers/allowed_groups.py)
   - Add `/allowed_groups` command handler
   - Add `mangrp:revoke` and `mangrp:keep` callback handlers

5. **strings.py**
   - Add new notification strings

6. **handlers/__init__.py**
   - Register new router if separate file

## Migration

On first run with new code:
- Existing `allowed_groups` entries remain as auto-approved
- New approvals go to `manual_approvals`
- No migration needed for existing data
