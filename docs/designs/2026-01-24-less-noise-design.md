# Less Noise Features Design

Date: 2026-01-24
Branch: less-noise

## Overview

Набор из 4 фич для уменьшения визуального шума в Telegram-боте:

1. **Verbose mode detailed menu** — расширенное меню `/verbose` с гранулярным контролем отображения tool calls
2. **Toggle bullet point** — вкл/выкл точки (●) в начале сообщений
3. **Thinking text display** — скрытие/форматирование `<thinking>` блоков
4. **Collapsible permission prompts** — сворачиваемые permission prompts с пагинацией

## Motivation

Сейчас бот генерирует много сообщений при активной работе Claude:
- Каждый tool call = отдельное сообщение с body
- Permission prompts показывают полный контент сразу
- Thinking блоки засоряют чат
- Нет гранулярного контроля — только verbose on/off

Пользователи хотят контролировать уровень детализации под свой workflow.

---

## Feature 1: Verbose Mode Detailed Menu

### Текущее состояние

`verbose` — boolean toggle (on/off):
- `off`: truncate до 5 строк, Bash до 500 символов
- `on`: полный вывод, Bash до 3500 символов

### Новая модель

Заменяем boolean на enum `DisplayMode`:

| Режим | Поведение |
|-------|-----------|
| `show_all` | Полный вывод без обрезки |
| `lines` | Truncate до N строк (настраиваемо) |
| `headers` | Только заголовки тулов без body |
| `current` | Одно сообщение, редактируется с каждым новым tool call |
| `silence` | Скрыть tool calls, показывать только текстовые ответы Claude |

Дополнительно: `line_limit: int` (дефолт 5) — используется в режиме `lines`.

### UI команды /verbose

Сообщение с текущим статусом + inline keyboard:

```
**Verbose mode**
Current: lines (10)
Truncate tool output to 10 lines

[show all]
[-5] [lines: 10] [+5]
[headers only]
[only current header]
[total silence]
[close]
```

При клике на кнопку:
- Настройка применяется сразу
- Текст сообщения обновляется с описанием выбранного режима
- [close] удаляет сообщение

### Миграция

- `verbose=true` → `display_mode=show_all`
- `verbose=false` → `display_mode=lines`, `line_limit=5`

---

## Feature 2: Toggle Bullet Point

### Описание

Toggle для включения/выключения точки (●) в начале сообщений о tool calls.

### Команда

`/display_bullet` — toggle on/off, показывается в `/settings`.

### Настройка

`display_bullet: bool` (дефолт `true` — включено, как сейчас).

### Изменения

В `format_tool_use()`:
- Если `display_bullet=true`: `● **Bash**: ...`
- Если `display_bullet=false`: `**Bash**: ...`

---

## Feature 3: Thinking Text Display

### Описание

Контроль отображения `<thinking>...</thinking>` блоков в текстовых сообщениях Claude.

### Команда

`/display_thinking_text` — toggle on/off, показывается в `/settings`.

### Настройка

`display_thinking_text: bool` (дефолт `true`).

### Поведение

**`display_thinking_text = ON` (дефолт):**
Показать курсивом, теги оставить:
```
*<thinking>
long reasoning text...
</thinking>*
```

**`display_thinking_text = OFF`:**
Заменить на сводку:
```
thinked • 150 symbols
```

### Изменения

Добавить обработку в pipeline перед отправкой текстовых сообщений:
- Найти блоки `<thinking>...</thinking>`
- Применить форматирование согласно настройке

---

### Сопутствующий рефакторинг

Переименовать существующую настройку:
- `feat_thinking_status` → `working_status`
- Команда `/exp_thinking_status` → `/working_status`

Это про индикатор "Claude работает", не связано с `<thinking>` блоками.

---

## Feature 4: Collapsible Permission Prompts

### Текущее состояние

Permission prompts показывают полный контент сразу. Длинные prompts разбиваются на несколько сообщений.

### Новое поведение

По умолчанию prompt свёрнут — только заголовок. Кнопка [Show more] раскрывает детали.
Настройки нет — всегда collapsed с возможностью развернуть.

### Одно сообщение вместо нескольких

Текущая проблема: permission prompt = 3-4 сообщения (body, options, 👆, keyboard).
При рестарте бота content сообщения зависают.

Решение: всегда одно сообщение с inline keyboard. Нечему зависать.

### UI: Collapsed (дефолт)

```
Bash: run tests

[1] Allow once for this conversation
[2] Always allow for this project
[3] Deny

[Show more]
[1] [2] [3]
```

Опции показываются текстом (полные), кнопки — сокращённые метки.

### UI: Expanded

```
Bash: run tests

────────────
[1/3] full body content chunk...
────────────

[1] Allow once for this conversation
[2] Always allow for this project
[3] Deny

[◀] [▶]
[Show less]
[1] [2] [3]
```

### При устаревании prompt

Если callback не находит processor или `last_body is None`:
1. Удаляем сообщение (`await callback.message.delete()`)
2. Сбрасываем state processor
3. Следующий poll покажет новый prompt

### Пагинация

- Длинный контент разбивается на чанки (~2000 символов для комфортного чтения)
- Кнопки [◀]/[▶] редактируют сообщение на предыдущий/следующий чанк
- Индикатор `[1/3]` показывает текущую позицию
- Если контент влезает в одно сообщение — [◀]/[▶] не показываются
- Всегда одно сообщение (не несколько)

### Рефакторинг chunker.py

Вынести core логику в helper:

```python
def _split_text(text: str, max_len: int) -> list[str]:
    """Split text at natural breakpoints (paragraphs → lines → sentences).

    Returns raw chunks without prefixes.
    """
    ...

def chunk_message(text: str, max_len: int = TELEGRAM_MESSAGE_MAX_LENGTH) -> list[str]:
    """Split and add [N/M] prefixes for multi-message sending."""
    chunks = _split_text(text, max_len - 10)  # reserve for [N/M]\n
    if len(chunks) > 1:
        chunks = [f"[{i+1}/{len(chunks)}]\n{c}" for i, c in enumerate(chunks)]
    return chunks
```

### Использование в permission prompts

```python
from codogram.chunker import _split_text

PERMISSION_PAGE_SIZE = 2000

# При подготовке prompt
body_chunks = _split_text(body, max_len=PERMISSION_PAGE_SIZE)
total_pages = len(body_chunks)
# markdown применяется при рендере каждой страницы
```

### Состояние в PermissionProcessor

Расширяем существующий processor (не отдельный dataclass):

```python
class PermissionProcessor(BaseProcessor):
    # Существующие поля
    self.state = PermissionState.IDLE
    self.last_body: str | None = None
    self.last_options: list[str] | None = None

    # Удаляем (было для нескольких сообщений)
    # self.content_msg_ids: list[int]
    # self.kb_msg_id: int | None

    # Новые поля
    self.msg_id: int | None = None      # одно сообщение
    self.expanded: bool = False
    self.current_page: int = 0
    self.chunks: list[str] | None = None
```

При callback проверяем `callback.message.message_id == processor.msg_id` для защиты от устаревших сообщений.

---

## Settings Display

### Текст (всегда полный):

```
**project-name**

chat
• /auto_accept: ● on
• /response_mode: all

claude
• mode: default
  (use /shift_tab to cycle)
• background tasks: 5
• context: 42%

ui
• /verbose_mode: lines (10)
• /display_bullet: ● on
• /display_thinking_text: ● on

experimental features
• /working_status: ○ off
• /exp_suggestions: ● on
• /exp_avatar_pack: ○ off
```

### Кнопки (пагинация):

**Группа 1 — chat:**
```
[/auto_accept]
[/response_mode]
[>]
```

**Группа 2 — ui:**
```
[/verbose_mode]
[/display_bullet]
[/display_thinking_text]
[<] [>]
```

**Группа 3 — experimental:**
```
[/working_status]
[/exp_suggestions]
[/exp_avatar_pack]
[<]
```

При нажатии [<]/[>] — edit message, меняются только кнопки.

---

## Data Model Changes

### ProjectState / ThreadInfo

Добавить:
```python
display_mode: str = "lines"  # show_all, lines, headers, current, silence
line_limit: int = 5
display_bullet: bool = True
display_thinking_text: bool = True
```

Переименовать:
```python
feat_thinking_status → working_status
```

Удалить:
```python
verbose: bool  # заменён на display_mode
```

### Миграция config.json

При загрузке старого конфига:
```python
if "verbose" in project:
    if project["verbose"]:
        project["display_mode"] = "show_all"
    else:
        project["display_mode"] = "lines"
        project["line_limit"] = 5
    del project["verbose"]

if "feat_thinking_status" in project:
    project["working_status"] = project["feat_thinking_status"]
    del project["feat_thinking_status"]
```

---

## Implementation Notes

### Порядок реализации

1. **Рефакторинг инфраструктуры** — chunker.py, модуляризация handlers/settings, вынос tool_formatter
2. **Data model changes** — новые поля, миграция verbose → display_mode
3. **Feature 2: Bullet toggle** — простой, разогрев
4. **Feature 3: Thinking text** — средняя сложность
5. **Feature 1: Verbose menu** — UI + логика режимов
6. **Feature 4: Collapsible prompts** — самая сложная, в конце
7. **Settings UI** — пагинация кнопок

### Out of Scope

- **AskUserQuestion** — не трогаем в этой итерации. Обкатаем подход на permission prompts, потом применим.

---

## File Architecture

### Модуляризация handlers/settings

```
handlers/settings/                    # NEW директория
├── __init__.py                       # router + include sub-routers
├── settings.py                       # перенести как есть
│                                     # TODO: модуляризировать в будущем
└── verbose_menu.py                   # NEW: /verbose_mode menu + callbacks
```

### Вынос tool_formatter из history_watcher

```
claude/
├── history_watcher.py                # watcher + парсинг jsonl (без форматирования)
└── tool_formatter.py                 # NEW: format_tool_use, _entry_to_messages
                                      # + display_mode logic
                                      # + bullet toggle
                                      # + thinking text processing
```

### Остальные файлы

| Файл | Изменения |
|------|-----------|
| `chunker.py` | Вынести `_split_text()` helper |
| `core/session_manager.py` | Новые поля, rename feat_thinking_status → working_status |
| `config.py` | Миграция при загрузке |
| `claude/poller/processors/permissions.py` | Collapsed UI, одно сообщение, пагинация |
| `telegram/keyboards/__init__.py` | Новые keyboards для permission prompts |
| `strings.py` | Тексты для меню и описаний |

### Обратная совместимость

- Миграция verbose → display_mode автоматическая при загрузке config
- Старые конфиги работают без изменений
- Команда /verbose открывает меню (вместо toggle)
