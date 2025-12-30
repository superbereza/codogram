# Codogram Setup

**[Русская версия](setup.ru.md)**

## Prerequisites

### Linux (Ubuntu/Debian)

```bash
# Python 3.10+ (via deadsnakes PPA if needed)
sudo apt update
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv

# tmux
sudo apt install tmux

# Claude Code CLI (native installer, recommended)
curl -fsSL https://claude.ai/install.sh | bash
```

### macOS

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Xcode Command Line Tools (required)
xcode-select --install

# Python 3.10+ (if not already installed)
brew install python

# tmux
brew install tmux

# Claude Code CLI (native installer, recommended)
curl -fsSL https://claude.ai/install.sh | bash
```

> **Note:** Don't use `sudo npm install -g` for Claude Code — it causes permission issues. The native installer is recommended.

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/codogram.git
cd codogram

# Run setup script (recommended)
./setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -e .
pip install -e ".[dev]"  # for development
```

## Configuration

### 1. Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram
2. Send `/newbot`
3. Follow instructions, get the token
4. **Important:** Enable "Allow Groups" in bot settings if you'll use it in groups

### 2. Get your Telegram ID

Send any message to [@userinfobot](https://t.me/userinfobot) — it will reply with your ID.

### 3. Configure .env

```bash
# Create .env file
cat > .env << 'EOF'
TELEGRAM_TOKEN=your_bot_token_here
ADMIN_IDS=123456789
EOF
```

Replace:
- `your_bot_token_here` — token from BotFather
- `123456789` — your Telegram ID

For multiple admins:
```bash
ADMIN_IDS=123456789,987654321
```

## Running

### Start the bot

```bash
# Activate venv (if not already)
source venv/bin/activate

# Start the bot
./restart.sh
```

### Autostart (Linux systemd)

```bash
# Create service file
sudo cat > /etc/systemd/system/codogram.service << EOF
[Unit]
Description=Codogram Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python -m codogram
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable codogram
sudo systemctl start codogram

# Check status
sudo systemctl status codogram
```

### Autostart (macOS launchd)

```bash
# Create plist file
cat > ~/Library/LaunchAgents/com.codogram.bot.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.codogram.bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(pwd)/venv/bin/python</string>
        <string>-m</string>
        <string>codogram</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$(pwd)</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$(pwd)/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$(pwd)/logs/stderr.log</string>
</dict>
</plist>
EOF

# Load and start
launchctl load ~/Library/LaunchAgents/com.codogram.bot.plist

# Check status
launchctl list | grep codogram
```

## Zero-Config Mode

Codogram works without any Claude configuration:

1. Start the bot: `./restart.sh`
2. Open tmux and start Claude Code in your project
3. Send `/start` in Telegram
4. Done!

### How it works

- **Session discovery**: Polls `~/.claude/history.jsonl` every 15s
- **Tmux discovery**: Scans tmux panes for matching cwd
- **Auto-reconnect**: Detects session changes (/new, /resume, /compact)
- **Cleanup**: Removes projects inactive > 30 days

## Usage

### Connect a project

```bash
# In Telegram:
/start              # Auto-detect project from chat name
/start myproject    # Explicit project name
```

This will:
1. Find the tmux session with this project
2. Start monitoring history.jsonl
3. Show permission prompts and tool calls

### Get your chat ID

```bash
# In Telegram:
/my_chat_id
```

## Troubleshooting

### Bot not responding

```bash
# Check if running
ps aux | grep codogram

# View logs
tail -20 logs/codogram.log

# Restart
./restart.sh
```

### Permission prompts not appearing

1. Check project is registered: `cat .config.json | jq '.projects'`
2. Verify tmux session is detected
3. Wait up to 15s (polling interval)

### Messages not reaching tmux

1. **Bot must be admin in the group** (Privacy Mode in Telegram)
2. Check tmux session is alive: `tmux ls`
3. Verify chat_id in config

### Git push fails with "Permission denied (publickey)"

Claude Code runs in a separate process without access to your SSH agent.

**Linux:**
```bash
# Install keychain
sudo apt install keychain

# Add to ~/.bashrc or ~/.zshrc
echo 'eval $(keychain --eval --quiet ~/.ssh/id_ed25519)' >> ~/.zshrc
source ~/.zshrc
```

**macOS:**
```bash
# SSH agent is built-in, add key to Keychain
ssh-add --apple-use-keychain ~/.ssh/id_ed25519

# Add to ~/.ssh/config
cat >> ~/.ssh/config << 'EOF'
Host *
  AddKeysToAgent yes
  UseKeychain yes
  IdentityFile ~/.ssh/id_ed25519
EOF
```

Replace `~/.ssh/id_ed25519` with your actual key path.

## Constraints

- One Claude per tmux session (split panes not supported)
- cwd fixed at /start (cd commands not tracked)
- Session changes detected within 15s (not instant)
