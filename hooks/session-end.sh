#!/bin/bash
# Claude Code SessionEnd hook
# Unregisters session from telegram-bridge

set -e

input=$(cat)
session_id=$(echo "$input" | jq -r '.session_id // empty')

if [ -z "$session_id" ]; then
    exit 0
fi

curl -s -X POST "http://localhost:8787/session/unregister" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$session_id\"}" >/dev/null 2>&1 || true

exit 0
