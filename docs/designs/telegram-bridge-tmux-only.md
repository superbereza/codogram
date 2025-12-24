# Telegram Bridge: tmux-only Design (PoC)

**Статус**: PoC / Альтернатива
**Дата**: 2025-12-23

## Идея

Вместо jsonl + tmux использовать **только tmux capture-pane** как источник данных.

**Текущий подход (jsonl + tmux):**
- jsonl для текста и событий
- tmux capture-pane только для permissions

**Альтернативный подход (tmux-only):**
- tmux capture-pane для всего
- jsonl опционально для границ (tool_use/tool_result)

## Архитектура

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│  Telegram   │◀───▶│  Bridge Server  │────▶│    tmux     │
└─────────────┘     └─────────────────┘     │ Claude Code │
                            │               └─────────────┘
                            │ capture-pane (polling 0.5s)
                            ▼
                    ┌───────────────┐
                    │ Screen Parser │
                    │  & Tracker    │
                    └───────────────┘
```

## Маркеры состояний

| Символ | Состояние | В Telegram |
|--------|-----------|------------|
| `●` (статичный) | Tool завершён / результат | Новое сообщение |
| `●` (контент растёт) | Tool работает | Edit сообщения (streaming) |
| `✶` | Думает (временно) | Игнорируем или status |
| `✓` | Завершено | Финальное сообщение |
| `❯` | Permission prompt | Inline кнопки |

## Структурированный diff

### Проблема

Простой diff строк не работает:
- Экран скроллится
- Progress перезаписывается
- Output растёт постепенно

### Решение: Block Tracking

Парсим capture в блоки по маркерам, отслеживаем по ID:

```python
@dataclass
class Block:
    marker: str      # ●, ✶, ✓, ❯
    tool: str | None # Bash, Read, Write...
    content: str

    @property
    def id(self) -> str:
        """Уникальный ID = маркер + tool + hash начала."""
        prefix = self.content[:50] if self.content else ""
        return f"{self.marker}:{self.tool}:{hash(prefix)}"

    @property
    def is_temporary(self) -> bool:
        return self.marker == "✶"

    @property
    def is_permission(self) -> bool:
        return self.marker == "❯" or "❯" in self.content


def parse_blocks(capture: str) -> list[Block]:
    """Парсим capture-pane output в список блоков."""
    blocks = []
    current_marker = None
    current_tool = None
    current_lines = []

    for line in capture.split("\n"):
        # Новый блок начинается с маркера
        marker_match = re.match(r'^([●✶✓])\s*(\w+)?\(?', line)
        if marker_match:
            # Сохраняем предыдущий блок
            if current_marker:
                blocks.append(Block(
                    marker=current_marker,
                    tool=current_tool,
                    content="\n".join(current_lines)
                ))
            current_marker = marker_match.group(1)
            current_tool = marker_match.group(2)
            current_lines = [line]
        elif current_marker:
            current_lines.append(line)

    # Последний блок
    if current_marker:
        blocks.append(Block(
            marker=current_marker,
            tool=current_tool,
            content="\n".join(current_lines)
        ))

    return blocks
```

### Screen Tracker

```python
class ScreenTracker:
    def __init__(self):
        self.blocks: dict[str, Block] = {}
        self.tg_messages: dict[str, int] = {}  # block_id -> msg_id

    async def process(self, capture: str, bot: Bot, chat_id: int):
        new_blocks = parse_blocks(capture)

        for block in new_blocks:
            if block.is_temporary:
                continue  # ✶ пропускаем

            if block.id not in self.blocks:
                # Новый блок → новое сообщение
                msg = await self.send_block(bot, chat_id, block)
                self.tg_messages[block.id] = msg.message_id

            elif self.blocks[block.id].content != block.content:
                # Контент изменился → edit
                msg_id = self.tg_messages.get(block.id)
                if msg_id:
                    await self.edit_block(bot, chat_id, msg_id, block)

        # Обновляем состояние
        self.blocks = {b.id: b for b in new_blocks if not b.is_temporary}

    async def send_block(self, bot, chat_id, block):
        text = self.format_block(block)

        if block.is_permission:
            kb = self.build_permission_keyboard(block)
            return await bot.send_message(chat_id, text, reply_markup=kb)

        return await bot.send_message(chat_id, text)

    def format_block(self, block: Block) -> str:
        if block.tool:
            return f"{block.marker} *{block.tool}*\n```\n{block.content[:500]}\n```"
        return f"{block.marker} {block.content[:1000]}"
```

## Main Loop

```python
async def watcher_task(bot: Bot, tmux_session: TmuxSession):
    tracker = ScreenTracker()

    while True:
        capture = tmux_session.capture_pane()
        await tracker.process(capture, bot, settings.chat_id)
        await asyncio.sleep(0.5)
```

## Преимущества

1. **Один источник данных** — только tmux
2. **Видим то же что в терминале** — WYSIWYG
3. **Автоматический streaming** — edit при изменениях
4. **Permissions из коробки** — ❯ детектится автоматически

## Недостатки

1. **Парсинг хрупкий** — зависит от формата вывода Claude Code
2. **Потеря истории** — если блок ушёл за экран, мы его не видим
3. **Нет metadata** — jsonl даёт tool_use_id, timestamps и т.д.

## PoC План

1. Написать `parse_blocks()` и протестировать на реальных capture
2. Написать `ScreenTracker` с базовой логикой
3. Заменить watcher_task на tmux-only версию
4. Протестировать end-to-end

## Сравнение с текущим подходом

| Аспект | jsonl + tmux | tmux-only |
|--------|--------------|-----------|
| Источники | 2 (jsonl + capture) | 1 (capture) |
| Надёжность | Выше (структурированный JSON) | Ниже (парсинг текста) |
| Streaming | Нужен отдельно | Из коробки |
| Permissions | Отдельная логика | Унифицировано |
| Сложность | Средняя | Низкая |

## Решение

Сначала протестировать PoC на реальных данных, потом решить какой подход лучше.
