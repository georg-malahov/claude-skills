# ralph

Native Claude-Code agentic loop. A clean replacement for the Docker-hosted ralphex flow, built as a single `/ralph` command with six subcommands. Runs in parallel with the existing `/orchestrate` and `/create-pr` from `dev-workflow` — nothing in this plugin replaces or modifies them.

## Pipeline

```
brainstorm  →  plan  →  execute  →  review  →  e2e  →  pr
   ↓           ↓ auto    ↓ auto      ↓ accumulate-loops back
   ↓           single   single        to plan via review-*.md
   ↓           or       or wave
   ↓           parallel
   ↓
docs/plans/.scratch/brainstorm-*.md (consumed by plan)
                                                                  
docs/plans/.scratch/review-*.md (consumed by plan, like brainstorm)
```

## Subcommands

| Command | Purpose |
|---|---|
| `/ralph brainstorm [topic]` | Interview-driven context gathering. Writes a dump that `plan` picks up. |
| `/ralph plan [description]` | Grill via `interview`, auto-route single vs parallel-wave mode, emit plan(s) + (if parallel) manifest. |
| `/ralph execute [resume]` | Native ralph-loop. Auto-detects single vs wave from manifest. No Docker. |
| `/ralph review [mode]` | Manual visual Q&A via `interview`. Modes: `accumulate` (logs follow-up dump) or `fix-now` (inline small commits). |
| `/ralph e2e [glob]` | Implement `FIXME(e2e)` placeholders one test at a time, in a separate session. |
| `/ralph pr [mode]` | Create a PR. Modes: `lean` (lint+type+unit) or `hardened` (adds E2E). Gated. |

## Subcommand independence

Every subcommand can run standalone — they reuse context from prior steps if present, otherwise they run cleanly from scratch:

- `/ralph plan` with no brainstorm/review dump → grills from scratch.
- `/ralph execute` with no plan → scans `docs/plans/` for unfinished plans and asks which to run.
- `/ralph review` with no execute context → walks recent uncommitted/unreviewed changes against the default branch.
- `/ralph e2e` with no FIXME markers → audits existing tests against current implementation: finds gaps in coverage, stale assertions, untested user-visible flows. The implicit ask becomes "what's missing or rotten?", not "what's marked."
- `/ralph pr` with no validation history → runs the gate fresh.

The pipeline shape (`brainstorm → plan → execute → review → e2e → pr`) is the **happy path**. Each subcommand is also a standalone tool.

## Session manifests — resume any session, any time

Every subcommand writes a manifest at `docs/plans/.scratch/session-<timestamp>-<slug>.md` with frontmatter (`kind`, `status: in_progress|completed|abandoned`, `started`, `updated`, `artifact`) and a checkpoint log appended at each meaningful step.

On invocation, every subcommand scans for `in_progress` manifests first. If one matches the current kind, offers Resume / Start new (abandon old) / Cancel. If one of a different kind is mid-flight, surfaces it as context.

This is the resumability contract: any session can be paused mid-stream (Ctrl+C, browser close, hardware crash) and picked up later without losing intent. See `commands/ralph.md` → "Session manifests" for the full spec.

## Surfaced bugs are owned

Across `/ralph execute`, the review loop, and `/ralph e2e`: if validation surfaces a failing test or error in code outside the current change, **fix it anyway**. A bug surfaced is a bug owned. The only exception is when the fix is substantial enough to be its own plan — then surface it to the user instead of silently scoping creep.

## What's deliberately out of the main loop

- **E2E execution.** During `execute`, user-visible behavior gets a `test.skip` + `FIXME(e2e): <scenario>` placeholder in `tests/e2e/`. `/ralph e2e` consumes these later, after the UI has settled via `/ralph review`.
- **Codex / external review tools.** Can be reintroduced as additional reviewer agents under `agents/` if needed.
- **Docker containers, image rebuilds, host-side dep dances.** Not needed in the native flow.

## Customization

Three-tier override chain (first match wins):
1. **Project:** `.claude/ralph/{agents,prompts}/<name>.md`
2. **Bundled:** `${CLAUDE_PLUGIN_ROOT}/agents,prompts/<name>.md` (this plugin)
3. Fail loud — no embedded fallback beyond the bundled defaults.

The five bundled review agents (`quality`, `implementation`, `testing`, `simplification`, `documentation`) are ported from the `theomedis-physio/.ralphex/agents/` set and tuned for the T3 + ZenStack + Better Auth + shadcn stack. Override any of them per project.

## Autonomous mode

If the user's request includes a phrase like `"implement autonomously and create pull request"`, the dispatcher sets `RALPH_AUTO_PR=true` and subsequent subcommands skip confirmation prompts:
- `plan` → chains into `execute` without asking
- `execute` → chains into `pr` (lean) without asking, or into `review` → `e2e` → `pr` (hardened) if the user also said `"hardened"` / `"with review"` / `"with e2e"`
- `pr` → skips the "Create PR?" confirmation

Without the phrase, every subcommand stops at its natural handoff and asks via `AskUserQuestion`.

## Coexistence with `/orchestrate` and `/create-pr`

This plugin is purely additive. `/orchestrate` (the ralphex-driven flow) keeps working unchanged. `/create-pr` keeps working unchanged. Use whichever fits the project — `/ralph` for new work, `/orchestrate` for projects already invested in the Docker flow.

## Loop budgets (matches originals)

| Loop | Cap | Source |
|---|---|---|
| Per-task | 2 dispatches (1 + 1 retry) | ralphex `task_retry_count=1`, cc-thingz `task_retries=1` |
| Outer task loop | 50 iterations safety | both originals |
| Review loop | 5 iterations (iter 1 = 5 agents, iter 2+ = 2 agents) | both originals merged |
| Review exit | all-clean OR HEAD-unchanged after fixer OR cap | ralphex HEAD short-circuit |
| Per-E2E-test | 3 fix iterations | ralph-specific |

Wave mode uses the same split as ralphex `--tasks-only`: per-wave plans run tasks-only (no review), the merge plan runs the full pipeline.

## Status

v0.1.0 — scaffold. Each subcommand is self-contained and independently testable on a small change. Order of validation against a real repo: `pr` (smallest surface) → `brainstorm` → `review` → `execute` single mode → `plan` single mode → `execute` wave mode → `plan` parallel mode → `e2e`.
