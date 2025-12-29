#!/bin/bash
# Check Message Delivery Script
#
# Verifies that all messages read from Claude jsonl were delivered to Telegram.
#
# Logging started: 2025-12-29 18:38 UTC+3
# Commit: 90590fc feat(watcher): add message delivery tracking logs
# https://github.com/superbereza/codogram/commit/90590fc

LOG_FILE="${1:-logs/codogram.log}"

if [[ ! -f "$LOG_FILE" ]]; then
    echo "Error: Log file not found: $LOG_FILE"
    echo "Usage: $0 [log_file]"
    exit 1
fi

echo "=== Message Delivery Check ==="
echo "Log file: $LOG_FILE"
echo ""

# Extract message IDs
READ_IDS=$(grep "message_read:" "$LOG_FILE" | sed -E 's/.*msg_id=([0-9a-f]+).*/\1/' | sort)
SENT_IDS=$(grep "message_sent:" "$LOG_FILE" | sed -E 's/.*msg_id=([0-9a-f]+).*/\1/' | sort)

READ_COUNT=$(echo "$READ_IDS" | grep -c .)
SENT_COUNT=$(echo "$SENT_IDS" | grep -c .)

echo "Messages read from jsonl: $READ_COUNT"
echo "Messages sent to Telegram: $SENT_COUNT"
echo ""

# Find lost messages
LOST=$(comm -23 <(echo "$READ_IDS") <(echo "$SENT_IDS"))
LOST_COUNT=$(echo "$LOST" | grep -c . || echo 0)

if [[ -z "$LOST" || "$LOST_COUNT" -eq 0 ]]; then
    echo "✅ All messages delivered successfully!"
else
    echo "❌ Lost messages: $LOST_COUNT"
    echo ""
    echo "Lost message IDs:"
    echo "$LOST"
    echo ""
    echo "Details:"
    for msg_id in $LOST; do
        grep "msg_id=$msg_id" "$LOG_FILE" | head -1
    done
fi

# Check for errors
ERROR_COUNT=$(grep -c "MESSAGE_LOST\|watch_thread_error" "$LOG_FILE" || echo 0)
if [[ "$ERROR_COUNT" -gt 0 ]]; then
    echo ""
    echo "⚠️  Errors found: $ERROR_COUNT"
    grep "MESSAGE_LOST\|watch_thread_error" "$LOG_FILE" | tail -5
fi
