# Claude Code: --resume ignores conversation context

**Severity:** High
**Status:** Waiting for Claude Code fix, no workaround found
**Related:** anthropics/claude-code#15837, #3138, #10161

## Description
Resume command uses correct session ID but Claude says "this is the beginning of our conversation".

## Symptoms
- `claude --resume <session_id>` executes successfully
- Session file exists with full history (675 lines)
- sessions-index.json has correct entry
- But model doesn't receive conversation context

## Impact on Codogram
Session resume feature doesn't restore context, making it useless for continuing work.

## Workaround
None found.
