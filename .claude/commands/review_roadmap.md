---
description: Review current roadmap status and active bugs
---

# Review Roadmap

Read the current state from:
1. `docs/ROADMAP.md` - Beta Test, In Progress, Backlog sections
2. `docs/bugs/active/` - Active bugs
3. `docs/bugs/testing/` - Testing bugs

Generate a formatted list in this exact format:

```
**Done** (only if items moved to Done since last review):
- **Item name** — was Beta Test
- **Item name** — new

**Beta Test** (count):
1. Item name
2. Item name
...

**In Progress** (count):
1. Item name
2. Item name
...

**Backlog** (count):
1. Item name
2. Item name
... (with --- separator after item 12 if more items exist)

**PoC / Research** (count):
1. Item name
...

---

**Bugs — Active** (count):

HIGH:
- bug-name (date)

MEDIUM:
- bug-name (date)
- bug-name (date)

MINOR:
- bug-name (date)
...

**Bugs — Testing** (count):
- bug-name (date)
...
```

Rules:
- Extract only `### Title` headers from roadmap sections (not descriptions)
- Sort bugs by severity (HIGH > MEDIUM > MINOR), within severity by date (newest first)
- Get bug severity from `**Severity:**` line in each bug file
- Get bug date from filename (YYYY-MM-DD prefix)
- Count items in each section and show in parentheses
- Use simple list format, no tables
- Mark changes since last review in this conversation:
  - Make changed item **bold**
  - Add comment after `—`: `**Item name** — was In Progress` or `**Item name** — new`
  - Examples: `**Avatar emoji pack** — was In Progress`, `**Tables rendering** — new`
