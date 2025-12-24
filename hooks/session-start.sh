#!/bin/bash
# Claude Code SessionStart hook
# Registers session with telegram-bridge

set -e

# Read JSON input from Claude
input=$(cat)

session_id=$(echo "$input" | jq -r '.session_id // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

if [ -z "$session_id" ]; then
    exit 0
fi

# Detect tmux session
tmux_session=$(tmux display-message -p '#S' 2>/dev/null || echo "")

# Register with telegram-bridge (fire and forget)
curl -s -X POST "http://localhost:8787/session/register" \
    -H "Content-Type: application/json" \
    -d "{
        \"session_id\": \"$session_id\",
        \"cwd\": \"$cwd\",
        \"tmux_session\": \"$tmux_session\"
    }" >/dev/null 2>&1 || true

exit 0
