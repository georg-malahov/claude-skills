# dev-workflow

Slash commands for the multi-wave ralphex orchestration workflow:

| Command | Purpose |
|---------|---------|
| `/orchestrate plan <description>` | Grill, decompose, emit lean per-wave plans + heavy merge plan + execution manifest |
| `/orchestrate execute` | Pre-flight check, launch ralphex with `--tasks-only`, monitor, run merge plan |
| `/orchestrate resume` | Pick up a paused orchestration |
| `/create-pr` | Open a GitHub PR — **gated on green validation** (lint + typecheck + unit + E2E) |
| `/fix-to-green` | Take multiple bug reports, categorize, apply test-first commits for bugs |
| `/preview-check` | Live-browser visual sanity check across mobile + desktop viewports |

## Install

```
/plugin marketplace add georg-malahov/claude-skills
/plugin install dev-workflow@georg-malahov-claude-skills
```

## Conventions assumed

- Bun + Next.js + Playwright project layout (commands reference `bun run lint && bun run typecheck && bun run test:unit && bun run test:e2e`)
- Docker dev container with a `bun run dx <cmd>` host wrapper (prefix all validation when running from host)
- Ralphex available as `ralphex` or `bin/ralphex-dk` in-project
- User-level `~/.claude/CLAUDE.md` defines "Run validation" semantics

Per-project overrides win — see project memory for command tweaks.
