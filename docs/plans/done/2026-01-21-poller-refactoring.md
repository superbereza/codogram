# Poller Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Рефакторинг 500-строчного poller.py в модульную структуру с отдельными processors.

**Architecture:** Разбиваем monolithic `claude/poller.py` на `claude/poller/` package с PollerContext, BaseProcessor и отдельными processors.

**Tech Stack:** Python 3.12, aiogram 3.x, asyncio

---

## Task 1: Create poller package structure

**Files:**
- Create: `src/codogram/claude/poller/__init__.py`
- Create: `src/codogram/claude/poller/context.py`
- Create: `src/codogram/claude/poller/base.py`

**Step 1: Create directory**

```bash
mkdir -p src/codogram/claude/poller/processors
```

**Step 2: Create context.py with PollerContext dataclass**

**Step 3: Create base.py with BaseProcessor class and helpers**

**Step 4: Create __init__.py with re-exports**

**Step 5: Commit**

```bash
git commit -m "refactor(poller): create poller package structure with context and base"
```

---

## Task 2: Create CompactProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/__init__.py`
- Create: `src/codogram/claude/poller/processors/compact.py`

Extract compact notification logic into CompactProcessor.

---

## Task 3: Create ThinkingProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/thinking.py`

Extract thinking status display logic.

---

## Task 4: Create SuggestionsProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/suggestions.py`

Extract input suggestions logic.

---

## Task 5: Create StuckProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/stuck.py`

Extract stuck message detection logic.

---

## Task 6: Create PermissionProcessor

**Files:**
- Create: `src/codogram/claude/poller/processors/permissions.py`

Extract permission prompt state machine (~150 строк).

---

## Task 7: Create crash.py and main poller loop

**Files:**
- Create: `src/codogram/claude/poller/crash.py`
- Create: `src/codogram/claude/poller/poller.py`

Extract crash detection and create main loop that orchestrates all processors.

---

## Task 8: Update imports and delete old poller.py

**Files:**
- Modify: `src/codogram/claude/__init__.py`
- Delete: `src/codogram/claude/poller.py`

Update all imports to use new package, delete old monolithic file.

**Test:**
```bash
python -c "from codogram.claude.poller import create_poller_task; print('OK')"
```

---

## Testing

После рефакторинга:
1. Запустить бота
2. Проверить permission prompts работают
3. Проверить thinking status работает
4. Проверить suggestions работают
5. Проверить compact notification работает
