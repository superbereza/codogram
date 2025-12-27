# Permission Content Display Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Показывать полный контент permission (diff, описание, вопрос) в Telegram и удалять после ответа.

**Architecture:** Расширяем парсер screen.py для извлечения контента между сепараторами. Храним message_id в dict, удаляем все связанные сообщения в callback handler.

**Tech Stack:** Python 3.11+, aiogram 3.x, tmux

**Design Doc:** `docs/designs/permission-content-display.md`

---

## Task 1: Расширить PermissionPrompt dataclass

**Files:**
- Modify: `agent-tools/codogram/src/codogram/screen.py`
- Modify: `agent-tools/codogram/tests/test_screen.py`

**Step 1: Добавить тест на парсинг контента**

```python
# tests/test_screen.py - добавить новый тест

PERMISSION_WITH_CONTENT = """
● Write(test.txt)

──────────────────────────────────────────────────────────
 Create file test.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 hello world
  2 line two
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to create test.txt?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. Type here to tell Claude what to do differently

 Esc to cancel
"""

def test_parse_permission_content():
    result = parse_screen(PERMISSION_WITH_CONTENT)
    assert isinstance(result, PermissionPrompt)
    assert result.description == "Create file test.txt"
    assert "hello world" in result.content
    assert "line two" in result.content
    assert result.question == "Do you want to create test.txt?"
    assert len(result.options) >= 2
```

**Step 2: Запустить тест — убедиться что падает**

Run: `cd agent-tools/codogram && pytest tests/test_screen.py::test_parse_permission_content -v`
Expected: FAIL (AttributeError: 'PermissionPrompt' object has no attribute 'description')

**Step 3: Расширить dataclass и парсер**

```python
# src/codogram/screen.py

@dataclass
class PermissionPrompt:
    options: list[str]           # ["1. Yes", "2. Yes, allow all..."]
    description: str = ""        # "Create file test.txt"
    content: str = ""            # diff/preview между ╌╌╌ маркерами
    question: str = ""           # "Do you want to create test.txt?"


def parse_screen(output: str) -> ScreenState:
    """Parse tmux capture-pane output to detect state."""

    # Permission prompt: look for ❯ marker with numbered options
    if "❯" in output:
        options = []
        description = ""
        content = ""
        question = ""

        lines = output.split("\n")

        # Parse options
        for line in lines:
            match = re.match(r'\s*[❯\s]\s*(\d+\.\s+.+)', line)
            if match:
                options.append(match.group(1).strip())

        if options:
            # Find description: first non-empty line after ─────
            in_header = False
            in_content = False
            content_lines = []

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Solid separator marks start of permission block
                if stripped.startswith("─" * 5):
                    in_header = True
                    continue

                # First line after solid separator is description
                if in_header and stripped and not description:
                    if not stripped.startswith("╌"):
                        description = stripped
                    continue

                # Dashed separator toggles content block
                if stripped.startswith("╌" * 5):
                    in_content = not in_content
                    continue

                # Collect content lines
                if in_content and stripped:
                    content_lines.append(line.rstrip())
                    continue

                # Question: line before options (contains "?")
                if "?" in stripped and not in_content:
                    # Check if next non-empty line has ❯
                    for j in range(i + 1, min(i + 5, len(lines))):
                        if "❯" in lines[j]:
                            question = stripped
                            break

            content = "\n".join(content_lines)

            return PermissionPrompt(
                options=options,
                description=description,
                content=content,
                question=question
            )

    # Tool progress: look for ● or ✶ with tool name
    progress_match = re.search(r'[●✶]\s*(\w+)\(([^)]*)\)', output)
    if progress_match and "❯" not in output:
        tool = progress_match.group(1)
        lines = output.strip().split("\n")
        output_lines = []
        for line in lines:
            if line.strip().startswith("⎿") or (line.strip() and not line.strip().startswith(("●", "✶", ">", "─"))):
                output_lines.append(line.strip())
        return ToolProgress(tool=tool, output="\n".join(output_lines[-5:]))

    return Idle()
```

**Step 4: Запустить тесты**

Run: `cd agent-tools/codogram && pytest tests/test_screen.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add agent-tools/codogram/src/codogram/screen.py agent-tools/codogram/tests/test_screen.py
git commit -m "feat(codogram): parse permission content from tmux"
```

---

## Task 2: Добавить константы и форматирование

**Files:**
- Modify: `agent-tools/codogram/src/codogram/main.py`

**Step 1: Добавить константы и функцию форматирования**

```python
# main.py - добавить после импортов

SEPARATOR_SOLID = "─" * 20
SEPARATOR_DASHED = "╌" * 20


def format_permission_content(perm: PermissionPrompt) -> str:
    """Format permission prompt for Telegram display."""
    parts = []

    if perm.description:
        parts.append(SEPARATOR_SOLID)
        parts.append(perm.description)

    if perm.content:
        parts.append(SEPARATOR_DASHED)
        parts.append(perm.content)
        parts.append(SEPARATOR_DASHED)

    if perm.question:
        parts.append(perm.question)

    return "\n".join(parts)
```

**Step 2: Commit**

```bash
git add agent-tools/codogram/src/codogram/main.py
git commit -m "feat(codogram): add permission content formatting"
```

---

## Task 3: Добавить хранение message_id

**Files:**
- Modify: `agent-tools/codogram/src/codogram/main.py`

**Step 1: Добавить глобальный dict**

```python
# main.py - после констант

# Track permission messages for deletion: {keyboard_msg_id: [content_msg_ids]}
permission_messages: dict[int, list[int]] = {}
```

**Step 2: Commit**

```bash
git add agent-tools/codogram/src/codogram/main.py
git commit -m "feat(codogram): add permission_messages storage"
```

---

## Task 4: Обновить polling loop для отправки контента

**Files:**
- Modify: `agent-tools/codogram/src/codogram/main.py`

**Step 1: Заменить логику в elif TOOL_USE блоке**

```python
# main.py - заменить блок elif entry.content_type == ContentType.TOOL_USE:

elif entry.content_type == ContentType.TOOL_USE:
    # Start polling for permission/progress
    s = get_session()
    last_state = None
    sent_content = False
    content_msg_ids: list[int] = []
    kb_msg = None

    while True:
        await asyncio.sleep(0.5)

        screen = s.capture_pane()
        state = parse_screen(screen)

        if isinstance(state, PermissionPrompt):
            if last_state != state.options:
                # Format and send content (only once)
                if not sent_content:
                    content_text = format_permission_content(state)
                    if content_text.strip():
                        for chunk in chunk_message(content_text):
                            try:
                                msg = await bot.send_message(
                                    settings.chat_id, chunk, parse_mode="Markdown"
                                )
                            except Exception:
                                msg = await bot.send_message(settings.chat_id, chunk)
                            content_msg_ids.append(msg.message_id)
                    sent_content = True

                # Send keyboard (new message or update existing)
                kb = permission_keyboard(state.options)
                if kb_msg:
                    try:
                        await kb_msg.edit_reply_markup(reply_markup=kb)
                    except Exception:
                        pass
                else:
                    kb_msg = await bot.send_message(
                        settings.chat_id, "👆", reply_markup=kb
                    )
                    # Track for deletion
                    permission_messages[kb_msg.message_id] = content_msg_ids

                last_state = state.options

        elif isinstance(state, ToolProgress):
            # Could update message with progress here
            pass

        else:
            # Idle - permission was handled or tool finished
            break
```

**Step 2: Commit**

```bash
git add agent-tools/codogram/src/codogram/main.py
git commit -m "feat(codogram): send permission content to Telegram"
```

---

## Task 5: Обновить callback handler для удаления сообщений

**Files:**
- Modify: `agent-tools/codogram/src/codogram/bot.py`

**Step 1: Добавить импорт и обновить handler**

```python
# bot.py - добавить импорт
from .main import permission_messages

# Заменить on_permission_callback:

@router.callback_query(F.data.startswith("perm:"))
async def on_permission_callback(callback: CallbackQuery):
    """Handle permission button press."""
    if callback.message.chat.id != settings.chat_id:
        return

    kb_msg_id = callback.message.message_id

    # Delete content messages
    content_ids = permission_messages.pop(kb_msg_id, [])
    for msg_id in content_ids:
        try:
            await callback.bot.delete_message(settings.chat_id, msg_id)
        except Exception:
            pass

    # Delete keyboard message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Send key to tmux
    action = callback.data.split(":")[1]
    s = get_session()

    if action == "esc":
        s.send_key("Escape")
    else:
        s.send_key(action)

    await callback.answer()
```

**Step 2: Commit**

```bash
git add agent-tools/codogram/src/codogram/bot.py
git commit -m "feat(codogram): delete permission messages on callback"
```

---

## Task 6: Интеграционный тест

**Step 1: Рестартовать бота**

```bash
/home/superbereza/dev/personal-agent/agent-tools/codogram/restart.sh
```

**Step 2: Тестирование**

1. Отправить в Telegram команду которая триггерит permission (например через другой Claude Code instance)
2. Проверить что появляется полный контент + кнопки
3. Нажать кнопку
4. Проверить что все сообщения удалились

**Step 3: Final commit (если нужны фиксы)**

```bash
git add -A
git commit -m "fix(codogram): permission content display fixes"
```

---

## Summary

| Task | Компонент | Ключевое |
|------|-----------|----------|
| 1 | Screen Parser | Парсинг description, content, question |
| 2 | Formatting | Константы сепараторов, format_permission_content() |
| 3 | Storage | permission_messages dict |
| 4 | Polling | Отправка контента + keyboard |
| 5 | Callback | Удаление всех сообщений |
| 6 | Testing | E2E проверка |
