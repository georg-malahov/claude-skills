# Review loop — unified

Single loop, two phases inside it. Pattern from cc-thingz `planning/exec` + ralphex `runClaudeReviewLoop` combined.

## Loop structure

**Cap: 5 iterations.** Track the current iteration N.

- **Iteration 1 — comprehensive.** Dispatch all 5 reviewer subagents in parallel:
  - `subagent_type: "ralph-quality"` (opus — security/multi-tenant)
  - `subagent_type: "ralph-implementation"` (sonnet — plan-vs-code)
  - `subagent_type: "ralph-testing"` (sonnet — unit coverage)
  - `subagent_type: "ralph-simplification"` (sonnet — over-engineering)
  - `subagent_type: "ralph-documentation"` (haiku — docs/READMEs)

- **Iterations 2–5 — critical re-check.** Dispatch 2 reviewer subagents in parallel, focused on Critical/Major only:
  - `subagent_type: "ralph-quality"`
  - `subagent_type: "ralph-implementation"`

Each subagent is a first-class Claude Code agent — its model and tools come from frontmatter in `agents/<name>.md`. Override per-project at `.claude/agents/ralph-<name>.md` (Claude Code merges plugin-bundled agents with project-local ones automatically).

## Per-iteration steps

1. **Capture HEAD before**: `git rev-parse HEAD` → `headBefore`.
2. **Fan out** the appropriate agent set (5 on iter 1, 2 on iter 2+) in a single message (parallel Agent tool calls). Subagents do NOT have the Agent tool — fan-out must be initiated from the orchestrator session.
3. **Aggregate findings.** Pass the **full unedited output of every agent** to the next step. Do NOT summarize or filter — that's the fixer's job.
4. **If all agents reported zero findings** → exit loop with status `clean`.
5. **Dispatch one fixer subagent**: `subagent_type: "ralph-fixer"` (sonnet) with the complete findings list. The fixer is the only one that touches code in this loop. Its contract lives in `agents/fixer.md`.
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

Lives in `agents/fixer.md` (the `ralph-fixer` subagent definition). Summary: receives full unedited findings list, decides what's actionable, commits each fix, re-runs lean validation, fixes surfaced bugs even in untouched code (unless substantial), outputs a `FIXES:` block listing fixed / skipped / new findings.

## What this loop does NOT do

- No per-finding parallelism. One fixer per round with the full list.
- No re-fan-out of all 5 agents in later iterations. Iterations 2+ are critical-only by design.
- No category-based selective re-runs (that was a non-standard invention). The 5→2 narrowing already replaces it.
- No "patience" stalemate counter beyond the HEAD short-circuit. The cap is the real safety.
- No E2E. That's `/ralph e2e`.
