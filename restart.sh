#!/bin/bash
cd "$(dirname "$0")"

# Kill existing process and wait for it to die
pkill -f "codogram.main" 2>/dev/null
for i in {1..10}; do
    pgrep -f "codogram.main" >/dev/null || break
    sleep 0.5
done

# Force kill if still alive
pkill -9 -f "codogram.main" 2>/dev/null
sleep 0.5

source ./venv/bin/activate

# Ensure logs directory exists
mkdir -p ./logs

PYTHONUNBUFFERED=1 nohup python -m codogram.main >> ./logs/codogram.log 2>&1 &
echo "Bot restarted (pid $!)"
