# Telegram Bridge Setup

## Zero-Config Mode (Default)

telegram-bridge now works without any Claude configuration:

1. Start bot: `./restart.sh`
2. Send `/start <project_name> <cwd>` in Telegram
3. Done! No hooks, no settings.json edits needed.

The bridge automatically discovers Claude sessions via `~/.claude/history.jsonl`.

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
BASE_DIR=/home/user/dev/personal-agent
```

- `TELEGRAM_TOKEN`: Get from @BotFather
- `ADMIN_IDS`: Comma-separated list of Telegram user IDs
- `BASE_DIR`: Path to personal-agent repository

## Installation

```bash
# Activate venv
cd ~/dev/personal-agent
source venv/bin/activate

# Install telegram-bridge
cd agent-tools/telegram-bridge
pip install -e .
```

## Running

```bash
# Start the bot
./restart.sh

# Check if running
ps aux | grep telegram_bridge

# View logs
tail -f ~/dev/personal-agent/tmp/telegram-bridge-logs/poller-debug.log
```

## Usage

### Register a project

```bash
# In Telegram, send:
/start myproject /path/to/project
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

1. Check if running: `ps aux | grep telegram_bridge`
2. Check logs: `tail -20 ~/dev/personal-agent/tmp/telegram-bridge-logs/poller-debug.log`
3. Restart: `./restart.sh`

### Permission prompts not appearing

1. Check session registered: `cat .config.json | jq '.projects'`
2. Verify tmux session detected correctly
3. Wait up to 15s for history.jsonl poll

### Messages not reaching tmux

1. Bot must be admin in Telegram group (Privacy Mode)
2. Check tmux session still running: `tmux ls`
3. Verify chat_id matches in config

## Migrating from Hooks (v1) to history.jsonl (v2)

If you were using the previous version with hooks, follow these steps:

### 1. Remove hooks from Claude settings

Edit `~/.claude/settings.json` and remove the hooks section:

```json
{
  "hooks": {
    "session_start": "...",   // ← DELETE
    "session_end": "..."      // ← DELETE
  }
}
```

### 2. Update bot

```bash
cd agent-tools/telegram-bridge
git pull origin main
./restart.sh
```

### 3. Reconnect projects

Send `/start <project_name> <cwd>` in each Telegram chat to reconnect.
The bot will auto-discover sessions from `~/.claude/history.jsonl`.

### Rollback

If you need to go back to hooks-based version:

```bash
git checkout with-hooks
./restart.sh
```

Then restore the hooks in `~/.claude/settings.json`.
