# Tone of Voice & Messages Spec

## Philosophy

Codogram talks like a helpful dev friend, not a corporate bot. Short, clear, no fluff.

## Status Indicators

All status prefixes in monospace:

| Symbol | Meaning | Example |
|--------|---------|---------|
| `[v]` | Success/Done | `[v]` Claude ready |
| `[x]` | Error/Fail/Cancel | `[x]` Timeout |
| `[!]` | Warning | `[!]` Session closed |
| `[~]` | Pending/In progress | `[~]` Starting Claude... |

Always wrap in backticks for Telegram markdown: `` `[v]` ``

## Tone Guidelines

### Do
- Be brief. "Clone error" not "An error occurred while cloning"
- Use lowercase after status prefix
- Direct instructions: "Use /start" not "Please use the /start command"
- Contractions ok: "doesn't", "can't"

### Don't
- No "Please", "Sorry", "Oops"
- No emojis (status indicators are enough)
- No exclamation marks except in `[!]` warnings
- No "successfully" - if it worked, just say what happened

## Message Patterns

### Success
```
`[v]` {what happened}

{optional details}
```

Example:
```
`[v]` Claude ready

Attach: `tmux attach -t claude-myproject`
```

### Error
```
`[x]` {what failed}: {why if known}
```

Examples:
```
`[x]` Timeout: Claude didn't start in 2 minutes
`[x]` Clone error: repository not found
`[x]` Launch error: tmux not installed
```

### Warning
```
`[!]` {what happened or what to watch out for}
```

Examples:
```
`[!]` Session closed: myproject
`[!]` Session not found. Make sure Claude is running.
```

### Pending
```
`[~]` {what's happening}...
```

Examples:
```
`[~]` Creating tmux session...
`[~]` Starting Claude...
`[~]` Cloning repository...
```

### Questions/Prompts

No status prefix. Just ask directly:

```
Launch?
Repository visibility?
Restart session `claude-myproject`?
```

### Instructions

No status prefix. Direct imperative:

```
Use /start first
Send project name (e.g. `my-project`):
Send repository URL:
```

## Button Labels

- Short: 1-3 words
- Action-oriented: "Yes, launch" not "Confirm launch"
- Cancel always: `[x] Cancel`

Examples:
- Yes, launch / No
- Yes, close / Cancel
- Yes, restart / Cancel
- Create / Different path
- Private / Public

## Error Messages Checklist

1. What failed? (required)
2. Why? (if known, after colon)
3. How to fix? (only if obvious and short)

Good:
```
`[x]` Clone error: repository not found
`[x]` Timeout: Claude didn't start in 2 minutes
`[!]` Session not found. Make sure Claude is running.
```

Bad:
```
❌ Oops! Something went wrong while trying to clone the repository. Please check if the URL is correct and try again.
```

## Flavor Text

Optional fun messages shown ~30% of the time after success status.

### Format

```
`[v]` Claude ready

{flavor text}

Attach: `tmux attach -t {name}`
```

### Rules

- No periods at end
- Ellipsis only for "action starting" phrases
- Lowercase after first word
- Keep it short (2-5 words)

### Time of Day

| Time | Flavor |
|------|--------|
| 5-9 | Early bird session starts… |
| 22-1 | Late night session starts… |
| 1-5 | Midnight hacking begins… |
| Weekend | Weekend warrior |

### Milestones

| Trigger | Flavor |
|---------|--------|
| Session #10 | Session #10. Getting warmed up |
| Session #50 | Session #50. Power user detected |
| Session #100 | Century club unlocked |
| 7 day streak | Week streak continues… |
| 30 day streak | Month streak |

### Moments

| Trigger | Flavor |
|---------|--------|
| First session today | First session today |
| 7+ days break | Long time no see |
| Friday 18:00+ | Friday evening deploy |
| 5+ sessions/day | Busy day |

### Random (~10% when no other trigger)

- Let's build something…
- Ready when you are
- Back to work
