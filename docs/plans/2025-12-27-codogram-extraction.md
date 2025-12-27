# Extraction Plan: telegram-bridge → codogram

## Goal

Extract `agent-tools/telegram-bridge` from personal-agent monorepo into standalone project `codogram` with full git history.

## Summary

| Aspect | Value |
|--------|-------|
| Source | `/home/superbereza/dev/personal-agent/agent-tools/telegram-bridge` |
| Target | `/home/superbereza/dev/codogram` |
| History | Full (240 commits), using `git filter-repo` |
| GitHub | New private repo `superbereza/codogram` |
| Package rename | `telegram_bridge` → `codogram` |
| After extraction | Delete from personal-agent |

## Steps

### Step 1: Preparation

```bash
# Install git-filter-repo
pip install git-filter-repo

# Ensure personal-agent is clean
cd /home/superbereza/dev/personal-agent
git status  # must be clean
git push    # push any pending commits
```

### Step 2: Extract with history

```bash
# Clone to temp folder (filter-repo requires fresh clone)
cd /tmp
git clone /home/superbereza/dev/personal-agent codogram-extract

# Apply filter-repo — keep only telegram-bridge
cd codogram-extract
git filter-repo --subdirectory-filter agent-tools/telegram-bridge
```

### Step 3: Move to final location

```bash
mv /tmp/codogram-extract /home/superbereza/dev/codogram
```

### Step 4: Copy runtime files (not in git)

```bash
# Copy .env (credentials)
cp /home/superbereza/dev/personal-agent/agent-tools/telegram-bridge/.env \
   /home/superbereza/dev/codogram/.env

# Copy logs
mkdir -p /home/superbereza/dev/codogram/tmp
cp -r /home/superbereza/dev/personal-agent/tmp/telegram-bridge-logs \
      /home/superbereza/dev/codogram/tmp/
```

### Step 5: Rename package telegram_bridge → codogram

```bash
cd /home/superbereza/dev/codogram

# Rename folder
mv src/telegram_bridge src/codogram

# Update all imports in code
find src tests -name "*.py" -exec sed -i 's/telegram_bridge/codogram/g' {} \;
find src tests -name "*.py" -exec sed -i 's/telegram-bridge/codogram/g' {} \;

# Update pyproject.toml
sed -i 's/telegram-bridge/codogram/g' pyproject.toml
sed -i 's/telegram_bridge/codogram/g' pyproject.toml

# Update restart.sh
sed -i 's/telegram_bridge/codogram/g' restart.sh
sed -i 's|/home/superbereza/dev/personal-agent/venv|/home/superbereza/dev/codogram/venv|g' restart.sh
sed -i 's/telegram-bridge/codogram/g' restart.sh

# Update CLAUDE.md and docs
sed -i 's/telegram_bridge/codogram/g' CLAUDE.md
sed -i 's/telegram-bridge/codogram/g' CLAUDE.md
find docs -name "*.md" -exec sed -i 's/telegram_bridge/codogram/g' {} \;
find docs -name "*.md" -exec sed -i 's/telegram-bridge/codogram/g' {} \;
```

### Step 6: Setup Python environment

```bash
cd /home/superbereza/dev/codogram
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### Step 7: Verify

```bash
# Run tests
pytest

# Check syntax
python3 -m py_compile src/codogram/main.py

# Try starting
./restart.sh
```

### Step 8: Create GitHub repo and push

```bash
cd /home/superbereza/dev/codogram
gh repo create codogram --private --source=. --push
```

### Step 9: Commit rename

```bash
git add -A
git commit -m "refactor: rename telegram_bridge to codogram"
git push
```

### Step 10: Cleanup personal-agent

```bash
cd /home/superbereza/dev/personal-agent

# Remove telegram-bridge
rm -rf agent-tools/telegram-bridge

# Remove logs
rm -rf tmp/telegram-bridge-logs

# Commit
git add -A
git commit -m "chore: remove telegram-bridge (moved to codogram repo)"
git push
```

### Step 11: Connect new Telegram chat

1. Start bot from `/home/superbereza/dev/codogram`
2. Run `/start` in new Telegram chat
3. Verify messages flow correctly

## Rollback

If something goes wrong:
- Original personal-agent repo is unchanged until Step 10
- Can re-clone from GitHub if needed
- `.env` stays in original location until manually deleted

## Files to update paths

| File | Changes needed |
|------|---------------|
| `restart.sh` | venv path, log path, module name |
| `CLAUDE.md` | All references to paths and package |
| `pyproject.toml` | Package name |
| `src/**/*.py` | All imports |
| `tests/**/*.py` | All imports |
| `docs/**/*.md` | References to telegram-bridge |
