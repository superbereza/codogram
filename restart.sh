#!/bin/bash
cd "$(dirname "$0")"

# Protect against running from worktree (use dev-run.sh instead)
if [[ "$PWD" == *".worktrees"* ]] && [[ "$1" != "--force" ]]; then
    echo "ERROR: Don't run restart.sh from worktree!"
    echo "Use ./dev-run.sh for testing, or ./restart.sh --force to override"
    exit 1
fi

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
