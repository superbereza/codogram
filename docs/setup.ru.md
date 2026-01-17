# Установка Codogram

**[English version](setup.md)**

## Требования

### Linux (Ubuntu/Debian)

```bash
# Python 3.10+ (через deadsnakes PPA если нужно)
sudo apt update
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv

# tmux
sudo apt install tmux

# Claude Code CLI (нативный установщик, рекомендуется)
curl -fsSL https://claude.ai/install.sh | bash
```

### macOS

```bash
# Homebrew (если ещё нет)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Xcode Command Line Tools (обязательно)
xcode-select --install

# Python 3.10+ (если ещё не установлен)
brew install python

# tmux
brew install tmux

# Claude Code CLI (нативный установщик, рекомендуется)
curl -fsSL https://claude.ai/install.sh | bash
```

> **Важно:** Не используй `sudo npm install -g` для Claude Code — это вызовет проблемы с правами. Нативный установщик рекомендуется.

## Установка

```bash
# Клонируй репозиторий
git clone https://github.com/yourusername/codogram.git
cd codogram

# Запусти скрипт установки (рекомендуется)
./setup.sh

# Или вручную:
python3 -m venv venv
source venv/bin/activate
pip install -e .
pip install -e ".[dev]"  # для разработки
```

## Настройка

### 1. Создай Telegram бота

1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. Отправь `/newbot`
3. Следуй инструкциям, получи токен
4. **Важно:** Включи "Allow Groups" в настройках бота, если будешь использовать в группах

### 2. Узнай свой Telegram ID

Отправь любое сообщение [@userinfobot](https://t.me/userinfobot) — он ответит твоим ID.

### 3. Настрой .env

```bash
# Создай .env файл
cat > .env << 'EOF'
TELEGRAM_TOKEN=your_bot_token_here
ADMIN_IDS=123456789
EOF
```

Замени:
- `your_bot_token_here` — токен от BotFather
- `123456789` — твой Telegram ID

Для нескольких админов:
```bash
ADMIN_IDS=123456789,987654321
```

## Запуск

### Запустить бота

```bash
# Активируй venv (если ещё не)
source venv/bin/activate

# Запусти бота
./stop-and-restart.sh
```

### Автозапуск (Linux systemd)

```bash
# Создай service файл
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

# Включи и запусти
sudo systemctl daemon-reload
sudo systemctl enable codogram
sudo systemctl start codogram

# Проверь статус
sudo systemctl status codogram
```

### Автозапуск (macOS launchd)

```bash
# Создай plist файл
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

# Загрузи и запусти
launchctl load ~/Library/LaunchAgents/com.codogram.bot.plist

# Проверь статус
launchctl list | grep codogram
```

## Режим без настройки

Codogram работает без настройки Claude:

1. Запусти бота: `./stop-and-restart.sh`
2. Открой tmux и запусти Claude Code в проекте
3. Отправь `/start` в Telegram
4. Готово!

### Как это работает

- **Session discovery**: Polls `~/.claude/history.jsonl` every 15s
- **Tmux discovery**: Scans tmux panes for matching cwd
- **Auto-reconnect**: Detects session changes (/new, /resume, /compact)
- **Cleanup**: Removes projects inactive > 30 days

## Использование

### Подключить проект

```bash
# В Telegram:
/start              # Автоопределение проекта по имени чата
/start myproject    # Указать проект явно
```

Это:
1. Найдёт tmux сессию с этим проектом
2. Начнёт мониторить history.jsonl
3. Покажет permission prompts и tool calls

### Узнать свой chat ID

```bash
# В Telegram:
/my_chat_id
```

## Решение проблем

### Бот не отвечает

```bash
# Проверь запущен ли
ps aux | grep codogram

# Посмотри логи
tail -20 logs/codogram.log

# Перезапусти
./stop-and-restart.sh
```

### Permission prompts не появляются

1. Проверь что проект зарегистрирован: `cat .config.json | jq '.projects'`
2. Проверь что tmux сессия найдена
3. Подожди до 15s (polling interval)

### Сообщения не доходят до tmux

1. **Бот должен быть админом группы** (Privacy Mode в Telegram)
2. Проверь что tmux сессия жива: `tmux ls`
3. Проверь chat_id в конфиге

### Git push fails с "Permission denied (publickey)"

Claude Code работает в отдельном процессе без доступа к SSH agent.

**Linux:**
```bash
# Установи keychain
sudo apt install keychain

# Добавь в ~/.bashrc или ~/.zshrc
echo 'eval $(keychain --eval --quiet ~/.ssh/id_ed25519)' >> ~/.zshrc
source ~/.zshrc
```

**macOS:**
```bash
# SSH agent уже встроен, добавь ключ в Keychain
ssh-add --apple-use-keychain ~/.ssh/id_ed25519

# Добавь в ~/.ssh/config
cat >> ~/.ssh/config << 'EOF'
Host *
  AddKeysToAgent yes
  UseKeychain yes
  IdentityFile ~/.ssh/id_ed25519
EOF
```

Замени `~/.ssh/id_ed25519` на путь к своему ключу.

## Ограничения

- Один Claude на tmux сессию (split panes не поддерживаются)
- cwd фиксируется при /start (cd не отслеживается)
- Обнаружение сессий с задержкой до 15 сек
