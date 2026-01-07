#!/bin/bash
# Run bot from current directory using PYTHONPATH (not pip install)
# Works from main or any worktree
# Config is always read from ~/.codogram/config.json

cd "$(dirname "$0")"

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
PYTHONPATH=src python -m codogram.main
