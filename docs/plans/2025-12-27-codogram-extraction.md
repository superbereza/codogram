# Extraction Plan: telegram-bridge → codogram

## Goal

Extract `agent-tools/telegram-bridge` from personal-agent monorepo into standalone project `codogram` with full git history, rename package, and seamlessly switch bot.

## Summary

| Aspect | Value |
|--------|-------|
| Source | `/home/superbereza/dev/personal-agent/agent-tools/telegram-bridge` |
| Target | `/home/superbereza/dev/codogram` |
| History | Full (240 commits), using `git filter-repo` |
| GitHub | New private repo `superbereza/codogram` |
| Package rename | `telegram_bridge` → `codogram` |
| Bot switch | One script: stop old → start new (minimal downtime) |
| Cleanup | Done by new Claude session in codogram |

## Steps

### Step 1: Extract with git filter-repo

```bash
pip install git-filter-repo

cd /tmp
git clone /home/superbereza/dev/personal-agent codogram-extract
cd codogram-extract
git filter-repo --subdirectory-filter agent-tools/telegram-bridge
```

### Step 2: Move to final location

```bash
mv /tmp/codogram-extract /home/superbereza/dev/codogram
```

### Step 3: Copy runtime files

```bash
# .env (credentials)
cp /home/superbereza/dev/personal-agent/agent-tools/telegram-bridge/.env \
   /home/superbereza/dev/codogram/.env

# Logs
mkdir -p /home/superbereza/dev/codogram/tmp
cp -r /home/superbereza/dev/personal-agent/tmp/telegram-bridge-logs \
      /home/superbereza/dev/codogram/tmp/
```

### Step 4: Rename package telegram_bridge → codogram

```bash
cd /home/superbereza/dev/codogram

# Rename folder
mv src/telegram_bridge src/codogram

# Update imports in code
find src tests -name "*.py" -exec sed -i 's/telegram_bridge/codogram/g' {} \;
find src tests -name "*.py" -exec sed -i 's/telegram-bridge/codogram/g' {} \;

# Update pyproject.toml
sed -i 's/telegram-bridge/codogram/g' pyproject.toml
sed -i 's/telegram_bridge/codogram/g' pyproject.toml

# Update restart.sh
sed -i 's/telegram_bridge/codogram/g' restart.sh
sed -i 's|/home/superbereza/dev/personal-agent/venv|/home/superbereza/dev/codogram/venv|g' restart.sh
sed -i 's/telegram-bridge/codogram/g' restart.sh

# Update docs
sed -i 's/telegram_bridge/codogram/g' CLAUDE.md
sed -i 's/telegram-bridge/codogram/g' CLAUDE.md
find docs -name "*.md" -exec sed -i 's/telegram_bridge/codogram/g' {} \;
find docs -name "*.md" -exec sed -i 's/telegram-bridge/codogram/g' {} \;
```

### Step 5: Setup Python environment

```bash
cd /home/superbereza/dev/codogram
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### Step 6: Verify

```bash
pytest
python3 -m py_compile src/codogram/main.py
```

### Step 7: Create GitHub repo

```bash
cd /home/superbereza/dev/codogram
git add -A
git commit -m "refactor: rename telegram_bridge to codogram"
gh repo create codogram --private --source=. --push
```

### Step 8: PROMPT REMINDER

**Перед переключением бота — сохрани этот промпт для нового Claude в codogram:**

```
Удали из personal-agent всё связанное с telegram-bridge:
- /home/superbereza/dev/personal-agent/agent-tools/telegram-bridge/
- /home/superbereza/dev/personal-agent/tmp/telegram-bridge-logs/
- План миграции уже выполнен, проект переехал в codogram

Закоммить и запуш:
git add -A && git commit -m "chore: remove telegram-bridge (moved to codogram repo)" && git push
```

### Step 9: Switch bot (one script, minimal downtime)

```bash
# Stop old bot
pkill -f "python -m telegram_bridge.main" || true
pkill -f "python -m codogram.main" || true

# Start new bot
cd /home/superbereza/dev/codogram
./restart.sh
```

### Step 10: Post-switch actions (manual)

1. В новом чате codogram выполнить `/start`
2. Проверить что personal-agent и bz-merch-assistant чаты работают (отправить сообщение)
3. Запустить Claude сессию в `/home/superbereza/dev/codogram`
4. Кинуть промпт из Step 8 новому Claude
5. Новый Claude удалит старые файлы и закоммитит

## Bot serves multiple projects

После миграции бот в codogram продолжит обслуживать:
- codogram (новый чат)
- personal-agent (существующий чат)
- bz-merch-assistant (существующий чат)

Конфиг `.config.json` сохраняется и содержит все привязки.

## Rollback

Если что-то пошло не так:
- Original personal-agent repo не изменён до Step 10
- Можно перезапустить старого бота: `cd /home/superbereza/dev/personal-agent/agent-tools/telegram-bridge && ./restart.sh`
