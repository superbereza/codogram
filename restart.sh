#!/bin/bash
cd "$(dirname "$0")"
pkill -f "codogram.main" 2>/dev/null
sleep 1
source /home/superbereza/dev/codogram/venv/bin/activate
PYTHONUNBUFFERED=1 nohup python -m codogram.main > /tmp/codogram.log 2>&1 &
echo "Bot restarted (pid $!)"
