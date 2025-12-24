#!/bin/bash
# Claude Code SessionStart hook
# Registers session with telegram-bridge

set -e

LOG_DIR="$HOME/dev/personal-agent/tmp/telegram-bridge-logs"
LOG_FILE="$LOG_DIR/session-hook.log"
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Read JSON input from Claude
input=$(cat)

log "SessionStart hook called"
log "Input: $input"

session_id=$(echo "$input" | jq -r '.session_id // empty')
cwd=$(echo "$input" | jq -r '.cwd // empty')

log "Parsed: session_id=$session_id, cwd=$cwd"

if [ -z "$session_id" ]; then
    log "ERROR: empty session_id, exiting"
    exit 0
fi

# Detect tmux session
tmux_session=$(tmux display-message -p '#S' 2>/dev/null || echo "")
log "Detected tmux_session=$tmux_session"

# Register with telegram-bridge
response=$(curl -s -X POST "http://localhost:8787/session/register" \
    -H "Content-Type: application/json" \
    -d "{
        \"session_id\": \"$session_id\",
        \"cwd\": \"$cwd\",
        \"tmux_session\": \"$tmux_session\"
    }" 2>&1) || true

log "curl response: $response"
log "SessionStart hook completed"

exit 0
