# MCP Trust Prompt Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect MCP server trust prompts and show them in Telegram as permission prompts (without auto-accept).

**Architecture:** Add `PromptType` enum to distinguish prompt types. Parse box-style MCP UI (`╭╮╯╰│`) in `screen.py`. Skip auto-accept for MCP prompts. Display and interaction identical to regular prompts.

**Tech Stack:** Python 3.11+, dataclasses, enum, regex, pytest

---

## Task 1: Add PromptType enum and update PermissionPrompt

**Files:**
- Modify: `src/codogram/screen.py:1-18`
- Test: `tests/test_screen.py`

**Step 1: Write test for existing behavior with new field**

```python
# Add to tests/test_screen.py
from codogram.screen import PromptType

def test_regular_prompt_has_regular_type():
    """Existing permission prompts should have REGULAR type."""
    result = parse_screen(PERMISSION_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert result.prompt_type == PromptType.REGULAR
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_screen.py::test_regular_prompt_has_regular_type -v`
Expected: FAIL with "cannot import name 'PromptType'"

**Step 3: Add PromptType enum and update dataclass**

```python
# In src/codogram/screen.py, add after imports
from enum import Enum

class PromptType(Enum):
    REGULAR = "regular"
    MCP_TRUST = "mcp_trust"

@dataclass
class PermissionPrompt:
    options: list[str]
    body: str = ""
    prompt_type: PromptType = PromptType.REGULAR
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_screen.py -v`
Expected: ALL PASS (including existing tests)

**Step 5: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py
git commit -m "feat(screen): add PromptType enum to PermissionPrompt"
```

---

## Task 2: Add _extract_options helper function

**Files:**
- Modify: `src/codogram/screen.py`
- Test: `tests/test_screen.py`

**Step 1: Write test for _extract_options**

```python
# Add to tests/test_screen.py
from codogram.screen import _extract_options

def test_extract_options_basic():
    """Extract options from lines with ❯ selector."""
    lines = [
        "Some body text",
        "More body",
        " ❯ 1. Yes",
        "   2. No",
        " Esc to cancel",
    ]
    body_lines, options = _extract_options(lines)
    assert options == ["1. Yes", "2. No"]
    assert "Some body text" in body_lines[0]

def test_extract_options_empty():
    """No ❯ means no options."""
    lines = ["Just text", "No selector here"]
    body_lines, options = _extract_options(lines)
    assert options == []
    assert len(body_lines) == 2

def test_extract_options_reusable():
    """_extract_options works in different contexts (MCP, regular, no-separator)."""
    # MCP-style content (stripped from box)
    mcp_lines = [
        "New MCP server found in .mcp.json: telegram",
        "",
        "❯ 1. Use this and all future MCP servers",
        "  2. Use this MCP server",
        "  3. Continue without",
    ]
    body, opts = _extract_options(mcp_lines)
    assert len(opts) == 3
    assert "MCP server" in body[0]

    # Regular permission style
    regular_lines = [
        "Do you want to create test.txt?",
        " ❯ 1. Yes",
        "   2. Yes, allow all",
        " Esc to cancel",
    ]
    body2, opts2 = _extract_options(regular_lines)
    assert opts2 == ["1. Yes", "2. Yes, allow all"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_screen.py::test_extract_options_basic -v`
Expected: FAIL with "cannot import name '_extract_options'"

**Step 3: Implement _extract_options**

```python
# Add to src/codogram/screen.py before parse_screen()

def _extract_options(lines: list[str]) -> tuple[list[str], list[str]]:
    """Extract options from lines containing ❯ selector.

    Returns:
        (body_lines, options) tuple
    """
    options = []
    body_lines = []
    in_options = False

    for line in lines:
        if "❯" in line:
            in_options = True
            match = re.match(r'\s*❯\s*(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())
        elif in_options:
            match = re.match(r'\s{2,}(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())
            elif line.strip().startswith(("Esc", "Enter")):
                break
        else:
            body_lines.append(line)

    return body_lines, options
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_screen.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py
git commit -m "refactor(screen): extract _extract_options helper"
```

---

## Task 2.5: Refactor existing functions to use _extract_options (DRY)

**Files:**
- Modify: `src/codogram/screen.py:52-81` (parse_screen)
- Modify: `src/codogram/screen.py:84-113` (_parse_options_without_separator)
- Test: `tests/test_screen.py`

**Step 1: Write regression test**

```python
# Add to tests/test_screen.py

def test_parse_screen_after_refactor():
    """Existing behavior unchanged after _extract_options refactoring."""
    # Regular permission prompt
    result = parse_screen(PERMISSION_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert len(result.options) >= 2
    assert "Yes" in result.options[0]
    # Body should contain file info
    assert "test.txt" in result.body
```

**Step 2: Run test to confirm it passes (before refactoring)**

Run: `pytest tests/test_screen.py::test_parse_screen_after_refactor -v`
Expected: PASS

**Step 3: Refactor parse_screen to use _extract_options**

```python
# In parse_screen(), replace lines 52-81 with:

    # Get lines after separator
    after_sep = lines[last_sep_idx + 1:]

    # Check: if there's ● after separator, it's not a permission prompt
    for line in after_sep:
        if re.match(r'^\s*●\s+\w+\(', line):
            return _check_tool_progress(output)

    # Use shared option extraction
    body_lines, options = _extract_options(after_sep)

    if not options:
        return _check_tool_progress(output)

    # Format body: replace ╌╌╌ with pretty separator
    body = "\n".join(body_lines)
    body = re.sub(r'╌{10,}', SEPARATOR_DASHED, body)
    body = body.strip()

    return PermissionPrompt(options=options, body=body)
```

**Step 4: Refactor _parse_options_without_separator**

```python
# Replace _parse_options_without_separator() with:

def _parse_options_without_separator(lines: list[str]) -> PermissionPrompt | None:
    """Parse permission prompt without solid separator (e.g., trust folder prompt).

    Looks for ❯ with numbered options even without ──── separator.
    """
    body_lines, options = _extract_options(lines)

    if not options:
        return None

    body = "\n".join(body_lines).strip()
    return PermissionPrompt(options=options, body=body)
```

**Step 5: Run all tests to verify no regression**

Run: `pytest tests/test_screen.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py
git commit -m "refactor(screen): use _extract_options in existing functions (DRY)"
```

---

## Task 3: Add _parse_mcp_trust_prompt function

**Files:**
- Modify: `src/codogram/screen.py`
- Test: `tests/test_screen.py`

**Step 1: Write tests for MCP prompt parsing**

```python
# Add to tests/test_screen.py

MCP_TRUST_SCREEN = """
╭──────────────────────────────────────────────────────────────────────╮
│ New MCP server found in .mcp.json: telegram                         │
│                                                                      │
│ ❯ 1. Use this and all future MCP servers in this project            │
│   2. Use this MCP server                                            │
│   3. Continue without using this MCP server                         │
╰──────────────────────────────────────────────────────────────────────╯
   Enter to confirm · Esc to reject
"""

def test_parse_mcp_trust_prompt_basic():
    """MCP trust prompt should be detected."""
    from codogram.screen import _parse_mcp_trust_prompt
    lines = MCP_TRUST_SCREEN.split("\n")
    result = _parse_mcp_trust_prompt(lines)
    assert result is not None
    assert isinstance(result, PermissionPrompt)
    assert len(result.options) == 3
    assert "Use this and all future" in result.options[0]

def test_parse_mcp_trust_prompt_type():
    """MCP prompt should have MCP_TRUST type."""
    from codogram.screen import _parse_mcp_trust_prompt
    lines = MCP_TRUST_SCREEN.split("\n")
    result = _parse_mcp_trust_prompt(lines)
    assert result.prompt_type == PromptType.MCP_TRUST

def test_parse_mcp_trust_prompt_body():
    """MCP prompt body should contain server name."""
    from codogram.screen import _parse_mcp_trust_prompt
    lines = MCP_TRUST_SCREEN.split("\n")
    result = _parse_mcp_trust_prompt(lines)
    assert "telegram" in result.body or "MCP server" in result.body

def test_parse_mcp_trust_prompt_incomplete():
    """Incomplete box (no ╰) should return None."""
    from codogram.screen import _parse_mcp_trust_prompt
    incomplete = """
╭─────────────────────────╮
│ Some content            │
│ ❯ 1. Option             │
"""
    result = _parse_mcp_trust_prompt(incomplete.split("\n"))
    assert result is None

def test_parse_mcp_trust_prompt_no_options():
    """Box without ❯ options should return None."""
    from codogram.screen import _parse_mcp_trust_prompt
    no_options = """
╭─────────────────────────╮
│ Just a box              │
│ No options here         │
╰─────────────────────────╯
"""
    result = _parse_mcp_trust_prompt(no_options.split("\n"))
    assert result is None

def test_parse_mcp_trust_prompt_last_box():
    """Multiple boxes on screen - should parse the LAST complete box."""
    from codogram.screen import _parse_mcp_trust_prompt
    multiple_boxes = """
Some scrollback text

╭─────────────────────────╮
│ Old box from scrollback │
│ ❯ 1. Old option         │
╰─────────────────────────╯

More text between boxes

╭─────────────────────────────────────────────────────╮
│ New MCP server found in .mcp.json: telegram         │
│ ❯ 1. Use this and all future MCP servers            │
│   2. Use this MCP server                            │
╰─────────────────────────────────────────────────────╯
   Enter to confirm
"""
    result = _parse_mcp_trust_prompt(multiple_boxes.split("\n"))
    assert result is not None
    # Should get options from the LAST box
    assert "Use this and all future" in result.options[0]
    assert "telegram" in result.body

def test_parse_mcp_trust_prompt_false_positive():
    """Box with ❯ but not in numbered format should return None."""
    from codogram.screen import _parse_mcp_trust_prompt
    false_positive = """
╭─────────────────────────╮
│ Some code output:       │
│ ❯ Not a real option     │
│ just arrow symbol       │
╰─────────────────────────╯
"""
    result = _parse_mcp_trust_prompt(false_positive.split("\n"))
    # No numbered options like "1. xxx" so should return None
    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_screen.py::test_parse_mcp_trust_prompt_basic -v`
Expected: FAIL with "cannot import name '_parse_mcp_trust_prompt'"

**Step 3: Implement _parse_mcp_trust_prompt**

```python
# Add to src/codogram/screen.py after _extract_options()

def _parse_mcp_trust_prompt(lines: list[str]) -> PermissionPrompt | None:
    """Parse MCP server trust prompt (box-style UI).

    Format:
    ╭────────────────────────────────╮
    │ New MCP server found...        │
    │ ❯ 1. Use this and all future   │
    │   2. Use this MCP server       │
    ╰────────────────────────────────╯
       Enter to confirm · Esc to reject

    Returns PermissionPrompt with MCP_TRUST type, or None if not MCP prompt.
    """
    # Find last box boundaries (in case of scrollback with multiple boxes)
    box_start = None
    box_end = None
    for i, line in enumerate(lines):
        if "╭" in line:
            box_start = i  # Take last ╭
        if "╰" in line and box_start is not None:
            box_end = i
            break  # Take first ╰ after last ╭

    if box_start is None or box_end is None:
        return None

    # Extract content between │...│
    content_lines = []
    for line in lines[box_start + 1 : box_end]:
        if "│" in line:
            # Split by │ and take middle content
            parts = line.split("│")
            if len(parts) >= 3:
                content_lines.append(parts[1].strip())
            elif len(parts) == 2:
                content_lines.append(parts[1].strip())

    if not content_lines:
        return None

    body_lines, options = _extract_options(content_lines)

    if not options:
        return None

    body = "\n".join(body_lines).strip()
    return PermissionPrompt(
        options=options,
        body=body,
        prompt_type=PromptType.MCP_TRUST
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_screen.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py
git commit -m "feat(screen): add _parse_mcp_trust_prompt for box-style UI"
```

---

## Task 4: Integrate MCP parsing into parse_screen

**Files:**
- Modify: `src/codogram/screen.py:23-40`
- Test: `tests/test_screen.py`

**Step 1: Write integration test**

```python
# Add to tests/test_screen.py

def test_parse_screen_detects_mcp_prompt():
    """parse_screen should detect MCP trust prompt."""
    result = parse_screen(MCP_TRUST_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert result.prompt_type == PromptType.MCP_TRUST
    assert len(result.options) == 3

def test_parse_screen_regular_still_works():
    """Regular prompts should still work and have REGULAR type."""
    result = parse_screen(PERMISSION_SCREEN)
    assert isinstance(result, PermissionPrompt)
    assert result.prompt_type == PromptType.REGULAR

def test_parse_screen_mcp_priority():
    """MCP prompt should be detected even if regular patterns also present."""
    # Screen with both MCP box AND regular separator
    mixed_screen = """
Some tool output
──────────────────────────────────────────────────────
Some text after separator

╭─────────────────────────────────────────────────────╮
│ New MCP server found in .mcp.json: telegram         │
│ ❯ 1. Use this and all future MCP servers            │
│   2. Use this MCP server                            │
╰─────────────────────────────────────────────────────╯
   Enter to confirm
"""
    result = parse_screen(mixed_screen)
    assert isinstance(result, PermissionPrompt)
    # MCP should take priority (parsed first)
    assert result.prompt_type == PromptType.MCP_TRUST
```

**Step 2: Run test to verify MCP detection fails**

Run: `pytest tests/test_screen.py::test_parse_screen_detects_mcp_prompt -v`
Expected: FAIL (returns Idle or wrong type)

**Step 3: Update parse_screen to try MCP first**

```python
# Modify parse_screen() in src/codogram/screen.py

def parse_screen(output: str) -> ScreenState:
    """Parse tmux capture-pane output to detect state.

    Parsing order (most specific first):
    1. MCP trust prompt (box-style) — ╭╮╯╰│ characters
    2. Regular permission prompt — ──── separator + ❯ options
    3. Permission without separator — ❯ options only (trust folder)
    4. Tool progress — ● or ✶ markers
    5. Idle — default
    """
    lines = output.split("\n")

    # 1. Try MCP trust prompt first (most specific)
    mcp_result = _parse_mcp_trust_prompt(lines)
    if mcp_result:
        return mcp_result

    # 2. Find last solid separator ────
    last_sep_idx = -1
    for i, line in enumerate(lines):
        if "─" * 10 in line:
            last_sep_idx = i

    # ... rest of existing code unchanged ...
```

**Step 4: Run all tests to verify**

Run: `pytest tests/test_screen.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/codogram/screen.py tests/test_screen.py
git commit -m "feat(screen): integrate MCP prompt detection into parse_screen"
```

---

## Task 5: Update auto_accept to check prompt_type

**Files:**
- Modify: `src/codogram/auto_accept.py`
- Test: `tests/test_auto_accept.py`

**Step 1: Write test for MCP prompt rejection**

```python
# Add to tests/test_auto_accept.py
from codogram.screen import PromptType

@pytest.mark.asyncio
async def test_try_auto_accept_skips_mcp_trust():
    """MCP trust prompts should never be auto-accepted."""
    tmux = MagicMock()
    queue = AsyncMock()

    result = await try_auto_accept(
        options=["1. Use this MCP server"],  # Would match "yes" pattern normally
        body="New MCP server found",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test-project",
        prompt_type=PromptType.MCP_TRUST,
    )

    assert result is False
    tmux.send_key.assert_not_called()
    queue.enqueue_nowait.assert_not_called()

@pytest.mark.asyncio
async def test_try_auto_accept_regular_still_works():
    """Regular prompts should still auto-accept."""
    tmux = MagicMock()
    queue = AsyncMock()

    result = await try_auto_accept(
        options=["1. Yes", "2. No"],
        body="Some prompt",
        tmux=tmux,
        telegram_queue=queue,
        chat_id=123,
        thread_id=None,
        context_name="test-project",
        prompt_type=PromptType.REGULAR,
    )

    assert result is True
    tmux.send_key.assert_called_once_with("1")

def test_auto_accept_types_whitelist():
    """Only REGULAR should be in AUTO_ACCEPT_TYPES whitelist."""
    from codogram.auto_accept import AUTO_ACCEPT_TYPES
    assert AUTO_ACCEPT_TYPES == {PromptType.REGULAR}
    # MCP_TRUST should NOT be in whitelist
    assert PromptType.MCP_TRUST not in AUTO_ACCEPT_TYPES
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_auto_accept.py::test_try_auto_accept_skips_mcp_trust -v`
Expected: FAIL with "unexpected keyword argument 'prompt_type'"

**Step 3: Update try_auto_accept signature and logic**

```python
# Modify src/codogram/auto_accept.py

from .screen import PromptType

# Add constant after AUTO_ACCEPT_PHRASES
AUTO_ACCEPT_TYPES = {PromptType.REGULAR}

async def try_auto_accept(
    options: list[str],
    body: str | None,
    tmux: TmuxSession,
    telegram_queue: "TelegramQueue",
    chat_id: int,
    thread_id: int | None,
    context_name: str,
    prompt_type: PromptType = PromptType.REGULAR,
) -> bool:
    """Try to auto-accept a permission prompt.

    Returns True if auto-accepted, False if manual mode needed.
    MCP trust prompts are never auto-accepted.
    """
    # Skip non-regular prompt types (e.g., MCP trust prompts)
    if prompt_type not in AUTO_ACCEPT_TYPES:
        logger.debug(f"Auto-accept: skipping {prompt_type.value} prompt")
        return False

    selected = select_option(options)
    # ... rest unchanged ...
```

**Step 4: Run tests to verify**

Run: `pytest tests/test_auto_accept.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/codogram/auto_accept.py tests/test_auto_accept.py
git commit -m "feat(auto_accept): skip MCP trust prompts"
```

---

## Task 6: Update permission_poller to pass prompt_type

**Files:**
- Modify: `src/codogram/permission_poller.py:181-184`

**Step 1: Update try_auto_accept call**

```python
# In permission_poller.py, find the try_auto_accept call and add prompt_type

if await try_auto_accept(
    parsed.options, parsed.body, tmux,
    telegram_queue, project.chat_id, thread_id, context_name,
    prompt_type=parsed.prompt_type,  # ADD THIS
):
```

**Step 2: Run existing tests**

Run: `pytest tests/test_permission_poller.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add src/codogram/permission_poller.py
git commit -m "feat(poller): pass prompt_type to try_auto_accept"
```

---

## Task 8: Add E2E test documentation

**Files:**
- Modify: `docs/e2e/commands/permissions.md`

**Step 1: Add MCP trust prompt test case**

```markdown
## MCP Trust Prompt

### PERM-MCP-001: MCP trust prompt detection

**Preconditions:**
- Project with `.mcp.json` configured
- New Claude session (MCP not yet trusted)

**Steps:**
1. `/start` in project with `.mcp.json`
2. Wait for MCP trust prompt to appear

**Expected:**
- Bot shows MCP prompt with 3 options in Telegram
- Buttons: "Use this and all future...", "Use this MCP server", "Continue without..."
- Cancel button present

**Verification:**
```bash
mcp__telegram__get_messages(chat_id=TEST_CHAT_ID, page_size=5)
# Should show MCP server trust prompt
mcp__telegram__list_inline_buttons(chat_id=TEST_CHAT_ID)
# Should show 4 buttons (3 options + Cancel)
```

### PERM-MCP-002: MCP prompt not auto-accepted

**Preconditions:**
- Auto-accept enabled for project
- New Claude session with `.mcp.json`

**Steps:**
1. Enable auto-accept: `/auto_accept`
2. `/start` new session

**Expected:**
- MCP trust prompt shown (NOT auto-accepted)
- Regular permission prompts still auto-accept

**Note:** MCP prompts require manual confirmation for security.
```

**Step 2: Commit**

```bash
git add docs/e2e/commands/permissions.md
git commit -m "docs(e2e): add MCP trust prompt test cases"
```

---

## Task 9: Update bug status and ROADMAP

**Files:**
- Move: `docs/bugs/active/2026-01-07-mcp-trust-prompt-not-detected.md` → `docs/bugs/done/`
- Modify: `docs/ROADMAP.md`

**Step 1: Move bug to done**

```bash
mv docs/bugs/active/2026-01-07-mcp-trust-prompt-not-detected.md docs/bugs/done/
```

**Step 2: Update ROADMAP - move MCP trust prompt to Done section**

Move the "MCP trust prompt support" item from Backlog to Done section with summary.

**Step 3: Commit**

```bash
git add docs/bugs/ docs/ROADMAP.md
git commit -m "docs: mark MCP trust prompt bug as fixed"
```

---

## Task 10: Final verification

**Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected: ALL PASS

**Step 2: Manual E2E test (optional)**

If test environment available:
1. Start bot with `./dev-run.sh`
2. Use Telegram MCP to test MCP prompt detection
3. Verify buttons work correctly

**Step 3: Final commit (if any fixes needed)**

```bash
git status
# If clean, done. If changes needed, commit them.
```
