# /whisper_stats Command Design

## Overview

Admin-only DM command to view Whisper API spending reports.

## Access Control

- DM only (private chat)
- Admin-only (ADMIN_IDS) — enforced by existing AdminMiddleware

## Data Source

`~/.codogram/whisper-usage.jsonl` — JSONL file with entries:
```json
{"ts": "2026-01-29T01:05:55", "user_id": 34185809, "username": "superbereza", "chat_id": -1003532995083, "project": "codogram", "duration_sec": 3, "file_size": 14122, "cost_usd": 0.0003, "success": true, "error": null}
```

## UI Design

### By Users Report (default)
```
📊 Whisper Usage (last 7 days)

By Users:
• @superbereza — $0.0018 (4 msgs)
• @another_user — $0.0012 (2 msgs)

Total: $0.0030

[← By Projects] [7d ✓] [30d] [All]
```

### By Projects Report
```
📊 Whisper Usage (last 7 days)

By Projects:
• codogram — $0.0025 (5 msgs)
• other-project — $0.0005 (1 msg)

Total: $0.0030

[← By Users] [7d ✓] [30d] [All]
```

### Empty State
```
📊 Whisper Usage (last 7 days)

No usage data for this period.

[← By Projects] [7d ✓] [30d] [All]
```

## Buttons

### Toggle Button (first)
- `← By Projects` — switches to projects report
- `← By Users` — switches to users report

### Period Buttons
- `7d` / `7d ✓` — last 7 days (default)
- `30d` / `30d ✓` — last 30 days
- `All` / `All ✓` — all time

Current period marked with ✓

## Callback Data Format

```
ws:<view>:<period>
```

- `view`: `users` | `projects`
- `period`: `7d` | `30d` | `all`

Examples:
- `ws:users:7d` — users report, 7 days
- `ws:projects:30d` — projects report, 30 days

## Implementation

### Files to Create/Modify

1. `src/codogram/handlers/whisper_stats.py` — new handler
   - `/whisper_stats` command
   - Callback query handler for buttons

2. `src/codogram/services/whisper_stats.py` — new service
   - `WhisperStatsService` class
   - `get_stats(view, period)` method
   - Reads and aggregates JSONL data

3. `src/codogram/strings.py` — add strings
   - `WHISPER_STATS_TITLE`
   - `WHISPER_STATS_BY_USERS`
   - `WHISPER_STATS_BY_PROJECTS`
   - `WHISPER_STATS_EMPTY`
   - `WHISPER_STATS_TOTAL`

4. `src/codogram/main.py` — register router

### Service Logic

```python
class WhisperStatsService:
    def get_stats(self, view: str, period: str) -> StatsResult:
        entries = self._load_entries(period)

        if view == "users":
            return self._aggregate_by_users(entries)
        else:
            return self._aggregate_by_projects(entries)

    def _load_entries(self, period: str) -> list[dict]:
        # Read JSONL, filter by period
        # period: "7d", "30d", "all"

    def _aggregate_by_users(self, entries) -> StatsResult:
        # Group by (user_id, username), sum cost_usd, count

    def _aggregate_by_projects(self, entries) -> StatsResult:
        # Group by project, sum cost_usd, count
```

### Keyboard Builder

```python
def build_stats_keyboard(current_view: str, current_period: str):
    toggle_text = "← By Projects" if current_view == "users" else "← By Users"
    toggle_view = "projects" if current_view == "users" else "users"

    periods = ["7d", "30d", "all"]
    period_buttons = [
        InlineKeyboardButton(
            text=f"{p} ✓" if p == current_period else p,
            callback_data=f"ws:{current_view}:{p}"
        )
        for p in periods
    ]

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"ws:{toggle_view}:{current_period}")],
        period_buttons
    ])
```
