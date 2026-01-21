---
description: Review current roadmap status and active bugs
---

# Review Roadmap

Read the current state from:
1. `docs/ROADMAP.md` - Done, Beta Test, In Progress, Backlog, PoC/Research sections
2. `docs/bugs/active/` - Active bugs
3. `docs/bugs/testing/` - Testing bugs
4. `docs/bugs/fixed/` - Fixed bugs (for today's date)
5. `git log --oneline -20` - Recent commits to identify what was done

Generate a formatted list in this exact format:

```
## Roadmap Review — YYYY-MM-DD

**Done today:**
- **Feature name** — was Beta Test
- **Feature name** — was In Progress
- 🐛 **bug-name** — fixed

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
... (with --- separator after item 14 if more items exist)

**PoC / Research** (count):
1. Item name
2. Item name
...

---

**Bugs — Active** (count):

HIGH:
- bug-name (date)

MEDIUM:
- bug-name (date)

MINOR:
- bug-name (date)

**Bugs — Testing** (count):
- bug-name (date)
```

Rules:
- Show today's date at the top (format: YYYY-MM-DD)
- **Done today** section:
  - Features moved to Done section in roadmap since last review
  - Bugs fixed today (check `docs/bugs/fixed/` for files with today's date prefix)
  - Mark bugs with 🐛 prefix
- Extract only `### Title` headers from roadmap sections (not descriptions)
- **PoC / Research**: show ALL items from this section
- Sort bugs by severity (HIGH > MEDIUM > MINOR), within severity by date (newest first)
- Get bug severity from `**Severity:**` line in each bug file
- Get bug date from filename (YYYY-MM-DD prefix)
- Count items in each section and show in parentheses
- Use simple list format, no tables
- Mark changes since last review in this conversation:
  - Make changed item **bold**
  - Add comment after `—`: `**Item name** — was In Progress` or `**Item name** — new`
- **Analyze git commits** (`git log --oneline --since="00:00"` for today):
  - Cross-reference commits with roadmap items and bugs
  - If commit indicates fix/feature completion not in roadmap — add to "Done today" with note
  - Ask user if roadmap needs updating based on commits
