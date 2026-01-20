#!/bin/bash
# Run bot from current directory using PYTHONPATH (not pip install)
# Works from main or any worktree
# Config is always read from ~/.codogram/config.json
#
# Usage:
#   ./kill-instance-and-start-from-worktree.sh        # foreground (blocks terminal)
#   ./kill-instance-and-start-from-worktree.sh --bg   # background (like stop-and-restart.sh)

cd "$(dirname "$0")"

# Parse --bg flag
RUN_IN_BG=false
if [[ "$1" == "--bg" ]]; then
    RUN_IN_BG=true
fi

# Find .env: current dir → main repo (for worktrees)
if [ -f .env ]; then
    ENV_FILE=".env"
elif [ -f ../../.env ]; then
    ENV_FILE="../../.env"
else
    echo "ERROR: .env not found in current dir or main repo"
    exit 1
fi

echo "Using env: $ENV_FILE"
echo "Using config: ~/.codogram/config.json"

# Export env vars (so pydantic-settings picks them up)
set -a
source "$ENV_FILE"
set +a

# Kill existing bot
pkill -f "codogram.main" 2>/dev/null
sleep 1

# Ensure logs directory
mkdir -p ./logs

# Run with local src (not installed package)
echo "Starting bot from: $PWD/src"
echo "Logs: ./logs/codogram.log"

if [[ "$RUN_IN_BG" == "true" ]]; then
    PYTHONPATH=src PYTHONUNBUFFERED=1 nohup python -m codogram.main >> ./logs/codogram.log 2>&1 &
    echo "Bot started in background (pid $!)"
else
    PYTHONPATH=src PYTHONUNBUFFERED=1 python -m codogram.main 2>&1 | tee -a ./logs/codogram.log
fi
