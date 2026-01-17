# Stuck Message Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically detect messages stuck in Claude's input line and push them through by sending Enter.

**Architecture:** Add `extract_input_text()` parser to screen.py, integrate stuck detection with debounce into permission_poller's main loop. Detect by matching input against `[Pasted X lines]` pattern or `thread.last_sent_message`.

**Tech Stack:** Python 3.10+, re module, existing permission_poller infrastructure

---

## Task 1: Add extract_input_text() to screen.py

**Files:**
- Modify: `src/codogram/screen.py:1-40` (add after imports)
- Test: `tests/test_screen.py`

**Step 1: Write the test**

```python
# tests/test_screen.py
import pytest
from codogram.screen import extract_input_text, PASTED_PATTERN


def test_extract_input_text_empty():
    screen = """────────────────────
❯
────────────────────"""
    assert extract_input_text(screen) is None


def test_extract_input_text_with_text():
    screen = """────────────────────
❯ hello world
────────────────────"""
    assert extract_input_text(screen) == "hello world"


def test_extract_input_text_pasted():
    screen = """────────────────────
❯ [Pasted 3 lines]
────────────────────"""
    result = extract_input_text(screen)
    assert result == "[Pasted 3 lines]"
    assert PASTED_PATTERN.match(result)


def test_extract_input_text_no_prompt():
    screen = """Some output
More output"""
    assert extract_input_text(screen) is None


def test_pasted_pattern_variants():
    assert PASTED_PATTERN.match("[Pasted 1 line]")
    assert PASTED_PATTERN.match("[Pasted 3 lines]")
    assert PASTED_PATTERN.match("[Pasted 100 lines]")
    assert not PASTED_PATTERN.match("hello world")
    assert not PASTED_PATTERN.match("[Pasted lines]")
```

**Step 2: Run test to verify it fails**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_screen.py::test_extract_input_text_empty -v`
Expected: FAIL with `ImportError` (function doesn't exist)

**Step 3: Add implementation**

Add to `src/codogram/screen.py` after line 4 (after `from enum import Enum`):

```python
# Pattern for pasted content placeholder
PASTED_PATTERN = re.compile(r'\[Pasted \d+ lines?\]')


def extract_input_text(screen: str) -> str | None:
    """Extract text from Claude's input line (after ❯).

    Returns None if input is empty or not found.
    Used for stuck message detection.
    """
    for line in screen.split("\n"):
        stripped = line.strip()
        if stripped.startswith("❯"):
            # Text after ❯
            text = stripped[1:].strip()
            return text if text else None
    return None
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/superbereza/dev/codogram && python -m pytest tests/test_screen.py -v -k "extract_input_text or pasted_pattern"`
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/screen.py tests/test_screen.py && git commit -m "$(cat <<'EOF'
feat(screen): add extract_input_text() for stuck message detection

Add PASTED_PATTERN regex and extract_input_text() function to parse
text from Claude's input line (after ❯ prompt).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add stuck detection to permission_poller

**Files:**
- Modify: `src/codogram/permission_poller.py:12` (add import)
- Modify: `src/codogram/permission_poller.py:117-126` (add state variables)
- Modify: `src/codogram/permission_poller.py:150-157` (add detection logic after crash detection)

**Step 1: Add import**

Update imports in `src/codogram/permission_poller.py` line 12:

```python
from .screen import parse_screen, PermissionPrompt, is_claude_ready, extract_input_text, PASTED_PATTERN
```

**Step 2: Add state variables**

Add after line 122 (`kb_msg_id: int | None = None`):

```python
    # Stuck message detection state
    stuck_input_text: str | None = None
    stuck_seen_count: int = 0
```

**Step 3: Add detection logic**

Add after crash detection block (after line 150 `return  # Exit poller`), before `is_permission = isinstance(parsed, PermissionPrompt)`:

```python
        # Stuck message detection (before permission state machine)
        input_text = extract_input_text(screen)
        if input_text:
            last_msg = thread.last_sent_message if thread else None

            is_potentially_stuck = (
                PASTED_PATTERN.match(input_text) is not None or
                (last_msg is not None and input_text == last_msg)
            )

            if is_potentially_stuck:
                if input_text == stuck_input_text:
                    stuck_seen_count += 1
                else:
                    stuck_input_text = input_text
                    stuck_seen_count = 1

                # Debounce: seen twice in a row = stuck, send Enter
                if stuck_seen_count >= 2:
                    logger.info(f"{log_prefix}: stuck message detected ({stuck_seen_count}x), sending Enter")
                    tmux.send_key("Enter")
                    # Clear state
                    stuck_input_text = None
                    stuck_seen_count = 0
                    # Clear last_sent_message to prevent re-triggering
                    if thread:
                        thread.last_sent_message = None
            else:
                # Not a stuck message, reset
                stuck_input_text = None
                stuck_seen_count = 0
        else:
            # No input text, reset
            stuck_input_text = None
            stuck_seen_count = 0
```

**Step 4: Verify syntax**

Run: `cd /home/superbereza/dev/codogram && python -c "from codogram.permission_poller import permission_poller; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
cd /home/superbereza/dev/codogram && git add src/codogram/permission_poller.py && git commit -m "$(cat <<'EOF'
feat(poller): add stuck message detection and auto-recovery

Detect messages stuck in Claude's input line by:
1. Matching [Pasted X lines] placeholder pattern
2. Matching thread.last_sent_message

With debounce (seen 2x in a row), send Enter to push through.
Clears last_sent_message after recovery to prevent re-triggering.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Manual testing

**Step 1: Restart bot**

```bash
/home/superbereza/dev/codogram/stop-and-restart.sh
```

**Step 2: Test with normal message**

Send a short message from Telegram. Verify:
- Message delivered to Claude
- No "stuck message detected" in logs

**Step 3: Test stuck detection (simulate)**

Check logs for stuck detection:
```bash
tail -f /home/superbereza/dev/codogram/logs/codogram.log | grep -i stuck
```

If a message gets stuck, should see:
```
INFO: Thread poller [xxx]: stuck message detected (2x), sending Enter
```

**Step 4: Commit docs update**

Update design checklist:

```bash
cd /home/superbereza/dev/codogram && git add docs/designs/2026-01-17-stuck-message-recovery.md && git commit -m "$(cat <<'EOF'
docs(design): mark stuck message recovery as implemented

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add extract_input_text() parser | screen.py, test_screen.py |
| 2 | Add stuck detection to poller | permission_poller.py |
| 3 | Manual testing | - |

**Total: 3 tasks, ~15 minutes**
