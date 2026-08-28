---
name: claude
description: Delegate coding, architecture review, film script writing, or technical tasks to Claude (Claude Sonnet 5 / Claude Opus via MiraiAPI). Activate this skill whenever the user asks to "use Claude", "ask Claude", "review with Claude", "delegate to Claude", or types `/claude`.
---

# Use Claude from Antigravity

This skill lets the Antigravity agent delegate coding, diagnosis, review, or creative tasks to the **Claude Agent** running via the bundled runner.

## Command Runner

```bash
node "C:\Users\hoang\.gemini\config\plugins\claude\scripts\claude-runner.mjs" task "<prompt>"
```

## Review Command

```bash
node "C:\Users\hoang\.gemini\config\plugins\claude\scripts\claude-runner.mjs" review "<diff or focus>"
```

## Rules
- When the user asks `/claude <task>`, immediately execute the runner with `task "<task>"` and return Claude's response.
- When the user asks `/claude review <target>`, execute `review "<target>"` and return the review.
