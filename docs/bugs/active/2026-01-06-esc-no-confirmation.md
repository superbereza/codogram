# /esc не отправляет подтверждение

**Найден в тесте:** F11
**Severity:** minor
**Status:** active

## Воспроизведение

1. Подключиться к сессии через /start
2. Отправить /esc

## Ожидаемый результат

Сообщение типа "`[~]` Escape sent" или аналогичное подтверждение

## Фактический результат

Никакого ответа. Пользователь не знает, сработала ли команда.

## Код

`src/codogram/handlers/sessions.py:67-88`:
```python
@router.message(Command("esc"))
async def cmd_esc(message: Message):
    # ... validation ...
    tmux.send_key("Escape")
    # ← Нет ответа пользователю!
```

## Фикс

Добавить ответ после отправки Escape:
```python
tmux.send_key("Escape")
await message.reply("`[~]` Escape sent", parse_mode="MarkdownV2")
```
