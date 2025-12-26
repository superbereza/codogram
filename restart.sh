#!/bin/bash
cd "$(dirname "$0")"
pkill -f "telegram_bridge.main" 2>/dev/null
sleep 1
source /home/superbereza/dev/personal-agent/venv/bin/activate
PYTHONUNBUFFERED=1 nohup python -m telegram_bridge.main > /tmp/telegram-bridge.log 2>&1 &
echo "Bot restarted (pid $!)"
