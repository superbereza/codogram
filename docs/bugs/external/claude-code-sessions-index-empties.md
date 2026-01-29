# Claude Code: sessions-index.json randomly empties

**Severity:** Medium
**Status:** Open, root cause unknown
**Related:** anthropics/claude-code#18311

## Description
Session index file becomes empty, breaking resume picker.

## Symptoms
- Caught on cook-guy and multiple other projects
- jsonl files exist but sessions-index.json has `"entries": []`
- Claude Code v2.1.23
- Root cause unknown — not Codogram's fault (we don't touch this file)

## Impact on Codogram
Resume picker doesn't work, sessions appear lost (though jsonl data is intact).

## Workaround
Manually restore index entry from jsonl data.
