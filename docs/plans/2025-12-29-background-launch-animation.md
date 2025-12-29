# Background Launch Animation Design

## Проблема

`launch_claude_new` блокирует event loop на 2-4 минуты:
- 3 сек начальный sleep
- 60 итераций × 1.5 сек анимации с `edit_text()`
- Rate limiting от Telegram

Последствия: бот не обрабатывает сообщения в других тредах пока анимация крутится.

## Решение

1. Background task для запуска (не блокирует handler)
2. Текстовые статусы вместо edit одного сообщения
3. Рожицы только если ждём > 3 сек (отдельное сообщение)
4. Все edit через TelegramQueue (rate limiter)

## Архитектура

### TelegramQueue — расширение для edit

```python
@dataclass
class OutgoingBatch:
    """Batch of messages to send atomically."""
    chat_id: int
    thread_id: int | None
    messages: list[dict]

@dataclass
class EditBatch:
    """Single message edit operation."""
    chat_id: int
    message_id: int
    text: str
    parse_mode: str | None = None

QueueItem = OutgoingBatch | EditBatch

class TelegramQueue:
    async def enqueue(self, item: QueueItem):
        """Add send or edit to queue."""
        ...

    async def _process_item(self, item: QueueItem):
        if isinstance(item, OutgoingBatch):
            await self._send_batch(item)
        elif isinstance(item, EditBatch):
            await self._edit_message(item)

    async def _edit_message(self, item: EditBatch, attempt: int = 0):
        MAX_ATTEMPTS = 3
        if attempt >= MAX_ATTEMPTS:
            return

        try:
            await self.bot.edit_message_text(
                chat_id=item.chat_id,
                message_id=item.message_id,
                text=item.text,
                parse_mode=item.parse_mode,
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await self._edit_message(item, attempt + 1)
        except TelegramBadRequest:
            pass  # Message deleted, ignore
```

### Рожицы (только уникальные)

```python
FACES = [
    "[._.]",   # Sleeping
    "[-_-]",   # Waking
    "[.o.]",   # Alert
    "[o_o]",   # Watching
    "[◉_◉]",   # Focused
    "[◉︿◉]",  # Tense
    "[°_°]",   # Confused
    "[°□°]",   # Shocked
    "[ಠ_ಠ]",   # Frustrated
    "[ಠ益ಠ]",  # Angry
    "[>_<]",   # Panic
    "[×_×]",   # Overload
    "[☠_☠]",   # Dead
]

FACE_READY = "[≖‿≖]"  # Happy/ready
```

### Flow анимации

```python
async def launch_with_animation(bot, chat_id, thread_id, project, thread, queue):
    try:
        # 1. Статусные сообщения
        await bot.send_message(chat_id, "Создаю tmux сессию...", message_thread_id=thread_id)
        create_tmux_with_claude(tmux_name, project.cwd)

        await bot.send_message(chat_id, "Запускаю Claude...", message_thread_id=thread_id)

        await bot.send_message(chat_id, "Жду готовность Claude...", message_thread_id=thread_id)

        # 2. Ждём готовности, анимация если > 3 сек
        tmux = TmuxSession(tmux_name, project.cwd)
        start_time = time.time()
        face_msg = None
        face_idx = 0

        while not tmux.is_claude_ready():
            elapsed = time.time() - start_time

            if elapsed > 3 and face_msg is None:
                # Первая рожица
                face_msg = await bot.send_message(
                    chat_id, f"`{FACES[0]}`",
                    parse_mode="Markdown",
                    message_thread_id=thread_id
                )
                face_idx = 1

            elif face_msg and face_idx < len(FACES):
                # Следующая рожица через queue
                await queue.enqueue(EditBatch(
                    chat_id=chat_id,
                    message_id=face_msg.message_id,
                    text=f"`{FACES[face_idx]}`",
                    parse_mode="Markdown",
                ))
                face_idx += 1

            await asyncio.sleep(3)  # Проверка каждые 3 сек

            if elapsed > 120:  # Timeout 2 min
                break

        # 3. Финал
        if face_msg:
            # Показать happy face
            await queue.enqueue(EditBatch(
                chat_id=chat_id,
                message_id=face_msg.message_id,
                text=f"`{FACE_READY}`",
                parse_mode="Markdown",
            ))
            await asyncio.sleep(1.5)
            await bot.delete_message(chat_id, face_msg.message_id)

        await bot.send_message(chat_id, "✓ Claude готов!", message_thread_id=thread_id)

        # 4. Запустить poller/watcher
        # ...

    except Exception as e:
        logger.error(f"launch_error: {e}")
        try:
            await bot.send_message(chat_id, f"❌ Ошибка запуска: {e}", message_thread_id=thread_id)
        except Exception:
            pass
        thread.awaiting_new_session = False
    finally:
        thread.launch_task = None
```

### Background task + race condition protection

```python
@router.callback_query(F.data == "start:launch_claude")
async def on_start_launch_claude(callback: CallbackQuery):
    project = project_manager.get_by_chat(callback.message.chat.id)
    thread = project.get_or_create_thread(thread_id, "main")

    # Проверка ДО создания task
    if thread.launch_task and not thread.launch_task.done():
        await callback.answer("⏳ Запуск уже идёт...")
        return

    await callback.answer()

    # Сохраняем reference
    thread.launch_task = asyncio.create_task(
        launch_with_animation(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            thread_id=thread.thread_id,
            project=project,
            thread=thread,
            queue=telegram_queue,
        )
    )
```

### ThreadInfo — новое поле

```python
@dataclass
class ThreadInfo:
    thread_id: int | None
    name: str
    session_id: str | None = None
    jsonl_path: str | None = None
    last_sent_message: str | None = None
    awaiting_new_session: bool = False
    # Tasks
    watcher_task: asyncio.Task | None = None
    poller_task: asyncio.Task | None = None
    binding_task: asyncio.Task | None = None
    launch_task: asyncio.Task | None = None  # NEW
```

## Порядок реализации

1. **TelegramQueue** — базовый rate limiter с `OutgoingBatch` + `EditBatch`
2. **Интеграция в main.py** — создать queue, передать в pollers
3. **Переписать launch_claude_new** — background task + анимация через queue
4. **Мигрировать pollers/watchers** — использовать queue вместо прямых вызовов

## Что решает

- Event loop не блокируется во время запуска
- Другие треды отвечают моментально
- Координация rate limit между анимацией и pollers
- Защита от параллельных запусков

## Зависимости

Этот дизайн расширяет существующий rate limiter:
- `docs/designs/2025-12-28-telegram-rate-limiter.md`
