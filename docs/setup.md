# Codogram Setup

## Zero-Config Mode

Codogram works without any Claude configuration:

1. Clone repo and setup environment
2. Start bot: `./restart.sh`
3. Send `/start` in Telegram
4. Done! Sessions are auto-discovered.

### How it works

- **Session discovery**: Polls `~/.claude/history.jsonl` every 15s
- **Tmux discovery**: Scans tmux panes for matching cwd
- **Auto-reconnect**: Detects session changes (/new, /resume, /compact)
- **Cleanup**: Removes projects inactive > 30 days

### Constraints

- One Claude per tmux session (split panes not supported)
- cwd fixed at /start (cd commands not tracked)
- Session changes detected within 15s (not instant)

## Environment Setup

Create `.env` file in the project root:

```bash
TELEGRAM_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321
```

- `TELEGRAM_TOKEN`: Get from @BotFather
- `ADMIN_IDS`: Comma-separated list of Telegram user IDs

## Installation

```bash
cd ~/dev/codogram
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Running

```bash
# Start the bot
./restart.sh

# Check if running
ps aux | grep codogram

# View logs
tail -f ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log
```

## Usage

### Register a project

```bash
# In Telegram, send:
/start              # Auto-detect project from chat name
/start myproject    # Explicit project name
```

This will:
1. Discover tmux session running in that directory
2. Poll history.jsonl for the session_id
3. Start monitoring permission prompts and tool calls

### Get your chat ID

```bash
# In Telegram, send:
/my_chat_id
```

Use this ID in `ADMIN_IDS` environment variable.

## Troubleshooting

### Bot not responding

1. Check if running: `ps aux | grep codogram`
2. Check logs: `tail -20 ~/dev/personal-agent/tmp/codogram-logs/poller-debug.log`
3. Restart: `./restart.sh`

### Permission prompts not appearing

1. Check session registered: `cat .config.json | jq '.projects'`
2. Verify tmux session detected correctly
3. Wait up to 15s for history.jsonl poll

### Messages not reaching tmux

1. Bot must be admin in Telegram group (Privacy Mode)
2. Check tmux session still running: `tmux ls`
3. Verify chat_id matches in config
