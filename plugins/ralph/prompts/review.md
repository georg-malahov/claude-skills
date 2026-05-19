# Review loop — unified

Single loop, two phases inside it. Pattern from cc-thingz `planning/exec` + ralphex `runClaudeReviewLoop` combined.

## Loop structure

**Cap: 5 iterations.** Track the current iteration N.

- **Iteration 1 — comprehensive.** Dispatch all 5 reviewer Agents in parallel:
  - `{{agent:quality}}`
  - `{{agent:implementation}}`
  - `{{agent:testing}}`
  - `{{agent:simplification}}`
  - `{{agent:documentation}}`

- **Iterations 2–5 — critical re-check.** Dispatch 2 reviewer Agents in parallel, focused on Critical/Major only:
  - `{{agent:quality}}`
  - `{{agent:implementation}}`

Each agent loads its file from `agents/<name>.md` via the override chain (project `.claude/ralph/agents/` → bundled).

## Per-iteration steps

1. **Capture HEAD before**: `git rev-parse HEAD` → `headBefore`.
2. **Fan out** the appropriate agent set (5 on iter 1, 2 on iter 2+) in a single message (parallel Agent tool calls). Subagents do NOT have the Agent tool — fan-out must be initiated from the orchestrator session.
3. **Aggregate findings.** Pass the **full unedited output of every agent** to the next step. Do NOT summarize or filter — that's the fixer's job.
4. **If all agents reported zero findings** → exit loop with status `clean`.
5. **Dispatch one fixer Agent** (general-purpose, bypassPermissions) with the complete findings list and the contract below. The fixer is the only one that touches code in this loop.
6. **Capture HEAD after**: `git rev-parse HEAD` → `headAfter`.
7. **HEAD short-circuit**: if `headAfter == headBefore` (fixer made no commits), exit loop with status `nothing-actionable` — the fixer judged the findings non-actionable or already-fixed. Surface to user.
8. **Re-run lean validation** (`lint → typecheck → test:unit`). If red: the fixer broke something, OR a pre-existing bug surfaced. Dispatch fixer again with the failing output as a new finding. This counts as part of the same iteration — does not consume an iteration slot.
9. **Advance iteration counter.** Loop.

## Exit on cap

If iteration 5 completes with findings still present:
- Report `review: max iterations reached, blocking issues remain`.
- Show the remaining Critical/Major findings to the user.
- Ask via AskUserQuestion: `fix manually` / `accept and continue (override)` / `abort`.

## Fixer contract

> You receive the FULL findings list from N reviewer agents. Decide what's real and actionable. For each actionable finding: fix it, commit with a clear message referencing the finding category.
>
> **Fix surfaced bugs even when out of scope.** When lean validation runs after your fixes, if it surfaces a failing test or type error in code you didn't touch this round, fix it anyway. A bug surfaced is a bug owned. Exception: if the fix would be substantial (new design decisions, >30 lines, schema migration), surface it as a finding for the user instead of silently fixing.
>
> If a finding contradicts the plan's stated intent: note it in the commit body and skip the fix.
> If a finding duplicates an already-fixed item (check `git log` for this session): skip silently.
> Do NOT make speculative changes or refactor adjacent code.
>
> Output a `FIXES:` section listing what was fixed and what was skipped (with reason).

## What this loop does NOT do

- No per-finding parallelism. One fixer per round with the full list.
- No re-fan-out of all 5 agents in later iterations. Iterations 2+ are critical-only by design.
- No category-based selective re-runs (that was a non-standard invention). The 5→2 narrowing already replaces it.
- No "patience" stalemate counter beyond the HEAD short-circuit. The cap is the real safety.
- No E2E. That's `/ralph e2e`.
