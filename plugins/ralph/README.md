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

- **E2E execution — capability-gated, mandatory when available.** `/ralph execute` Step 1 runs an environment probe; there is **no mode menu**:
  - **E2E runnable (`dev+prod`)**: each task authors + runs its own E2E spec against a warm dev server (single mode; green required to finish), and a full prod-build suite runs as a mandatory gate after the review loop.
  - **E2E exists but no dev path (`prod-only`)**: no per-task E2E; the full prod gate still runs after review.
  - **E2E not runnable (`unsupported`)**: lean-only automatically — user-visible behavior gets a `test.skip` + `FIXME(e2e): <scenario>` placeholder in `tests/e2e/`, which `/ralph e2e` consumes later.
- **Codex / external review tools.** Can be reintroduced as additional reviewer agents under `agents/` if needed.
- **Docker containers, image rebuilds, host-side dep dances.** Not needed in the native flow.

## Customization

Three-tier override chain (first match wins):
1. **Project:** `.claude/ralph/{agents,prompts}/<name>.md`
2. **Bundled:** `${CLAUDE_PLUGIN_ROOT}/agents,prompts/<name>.md` (this plugin)
3. Fail loud — no embedded fallback beyond the bundled defaults.

Bundled subagents (registered as first-class Claude Code agents via plugin manifest, with `name` / `model` / `tools` in frontmatter):

| Subagent | Model | Effort | Color | Role |
|---|---|---|---|---|
| `ralph-quality` | opus | **xhigh** | red | Security, multi-tenant safety, ZenStack policy gaps, TS correctness |
| `ralph-implementation` | sonnet | — | blue | Plan-vs-code correctness |
| `ralph-testing` | sonnet | — | green | Unit-test coverage and quality (no E2E) |
| `ralph-simplification` | sonnet | — | yellow | Over-engineering, dead code, premature abstractions |
| `ralph-documentation` | haiku | — | gray | README / ADR / inline-doc updates |
| `ralph-task` | sonnet | — | purple | Implements one plan task; preloads `verification-before-completion`; Skill access for TDD/design/SEO/debugging |
| `ralph-fixer` | sonnet | — | orange | Applies findings from one review round; preloads `verification-before-completion`; Skill access |

Five review agents ported from `theomedis-physio/.ralphex/agents/` and tuned for T3 + ZenStack + Better Auth + shadcn. Override any subagent per project by dropping `.claude/agents/ralph-<name>.md` into the project — Claude Code merges plugin-bundled and project-local agents automatically.

Model choices follow the theomedis pattern: opus for the high-stakes security review, haiku for cheap text work, sonnet for the balanced middle. Override per project by changing `model:` in the local agent file.

### Tool grants

| Subagent | Tools | Notes |
|---|---|---|
| `ralph-quality` | `Read, Grep, Glob, Bash` | Read-only |
| `ralph-implementation` | `Read, Grep, Glob, Bash` | Read-only |
| `ralph-testing` | `Read, Grep, Glob, Bash` | Read-only |
| `ralph-simplification` | `Read, Grep, Glob, Bash` | Read-only |
| `ralph-documentation` | `Read, Grep, Glob, Bash` | Read-only |
| `ralph-task` | `Read, Write, Edit, Grep, Glob, Bash, Skill` | Skill access for TDD, frontend, SEO, debugging |
| `ralph-fixer` | `Read, Write, Edit, Grep, Glob, Bash, Skill` | Skill access for debugging, polish, verification |

**No MCP tools, no WebFetch, no WebSearch** — by design. The loop is deterministic and offline-capable.

### Hardening Bash for review agents (optional)

Claude Code does **not** allow per-subagent `Bash(<pattern>:*)` restrictions in the `tools:` frontmatter — those patterns only work in `permissions.allow` at the session level. If a project wants tighter Bash for the review phase, add to `.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Bash(rm:*)", "Bash(curl:*)", "Bash(wget:*)"
    ]
  }
}
```

That applies to the whole session, not just review agents, but it's the closest we can get to "review agents can only diff/log."

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

Wave mode is single mode multiplied: the orchestrator runs one per-task loop per plan concurrently, each plan in its own git worktree. Same per-task `ralph-task` dispatch and fresh-context-per-task as single mode — within a plan tasks stay sequential, across plans they run in parallel. The orchestrator is the single dispatcher (every `ralph-task` is a leaf subagent — no nesting). Per-wave plans run tasks-only; the final merge plan runs the full pipeline including the review loop.

## Execute is event-driven — the session stays free

`/ralph execute` does not block the session for the whole run. It is an **event-driven orchestrator**: each invocation reconciles state, does one step, and ends its turn.

- Each task is dispatched as a **background** subagent. The orchestrator then ends its turn → the session is free, you can ask "check progress" or "pause" or anything else.
- When a background subagent completes, the Claude Code harness **automatically re-invokes** the orchestrator — no polling, no sleep. It reads the result, advances to the next task, ends its turn again.
- The loop auto-advances without you typing "continue". On `TASK_FAILED` after a retry, it stops and asks you what to do.

Durable state lives in the plan file (`[ ]`/`[x]`) and the session manifest — so any invocation, even after a crash, rebuilds full context from disk.

Every `/ralph` run prints a `ralph v<version> — <subcommand>` banner, and `execute` writes that version as the first line of every progress file — so you can always tell which plugin version a session or a run is on (plugin files load once at session start; a session keeps its loaded version even after the marketplace updates).

## Environment probe + capability-driven dev server

`/ralph execute` Step 1 runs a **hardened environment probe** that determines how the project runs and what can actually run — then verifies by probing, because a fresh git worktree has no `node_modules`. It resolves:

- **`run_prefix`** — empty on host-native projects, `bun run dx` (or equivalent) on Docker-in-container projects. Every lean-validation and E2E command, in the orchestrator and in each task, goes through it. ralph itself manages no containers/images — it delegates to the project's wrapper.
- **deps ready?** — if `node_modules` can't run lean validation, the orchestrator **auto-installs once on the host** (`bun install`, or `bun run up` for a Docker project) and re-verifies; if it still can't run, it **hard-stops** rather than dispatch onto a broken environment.
- **`e2e`** — `dev+prod` / `prod-only` / `unsupported`, which drives everything below.

**Dev server is capability-driven.** By default (`e2e: unsupported` / `prod-only`, and all wave mode) **no dev server** — lean validation needs no running app, and a `next dev` watcher is pure waste (in wave mode, a recompile storm across N worktrees). The **exception**: `e2e: dev+prod` in single mode keeps exactly **one** warm dev server alive for the run — the recompiles are the hot-reload that lets each task run its freshly-authored spec immediately, and single mode runs one task at a time, so there's one server and no storm. Per-task dev E2E is **single-mode only this phase**; wave gets E2E via the mandatory prod gate (S3.5) on the merged app. `/ralph e2e` remains the standalone manager of its own server.

## Progress files — runtime introspection

Subagents run in isolated context windows; the main session only sees their final summary. To see what an agent is doing *mid-run* (and catch it circling), each run writes a progress file:

```
${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt
```

Modeled on cc-thingz `planning/exec` — two bundled scripts (`scripts/init-progress.sh`, `scripts/append-progress.sh`) own the format. The orchestrator logs coarse milestones (`[orch]`, `[review]`, `[fixer-summary]`); the running task/fixer subagents log fine-grained milestones (`[task]`, `[fixer]`) so mid-task circling is visible.

A temp dir is deliberate: the progress file is throwaway telemetry, **not** resume state. Resume reads the plan checkboxes + session manifest. The progress file is never committed, never in `git status`. `${TMPDIR:-/tmp}` resolves to a private per-user temp dir on macOS and `/tmp` on Linux — check it any time with `tail -30 "${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt"`.

When you ask "check progress", the orchestrator reads the tail and explicitly flags circling signals: repeated `validation: X FAIL`, repeated `decision: revert`, or a long stale gap.

## Cloud deployment

The plugin is just markdown — no binaries, no Docker, no native dependencies. It runs anywhere Claude Code runs, with three caveats: where the plugin *files* live, where session state persists, and what runtime tools must be preinstalled.

### Where can `ralph` actually be installed?

Claude Code has three plugin scopes:

| Scope | Location | Lifetime | Best for |
|---|---|---|---|
| **User-level** | `~/.claude/plugins/` (or equivalent), installed via `/plugin install` from a marketplace | Persists across projects for that user; lost in ephemeral cloud envs unless that directory is mounted/persisted | Local development on your own machine |
| **Repo-vendored** | `.claude/plugins/ralph/` checked into the project repo | Travels with the repo; works in any cloud env that clones the repo | CI runners, ephemeral cloud VMs, shared team setups |
| **Pre-baked image** | Installed at image-build time (e.g. in a Dockerfile for a cloud dev container) | Lives for the image's lifetime; rebuilds when the image rebuilds | Fleet of identical cloud workstations, GitHub Codespaces, gitpod, etc. |

### Will it exist in a cloud environment?

Only if you put it there. A fresh cloud container has no plugins by default — Claude Code starts clean. Three options:

**Option 1 — Vendor into the project repo (most reliable).** Copy `plugins/ralph/` to `<your-project>/.claude/plugins/ralph/` and commit it. Every clone of the project gets the plugin automatically. Trade-off: plugin updates require a manual sync from the source repo. Good for teams where the workflow shouldn't drift per-developer.

**Option 2 — Install on session start.** Add a startup hook or boot script that runs the equivalent of `claude plugin add georg-malahov/claude-skills && claude plugin install ralph` when the cloud env spins up. Requires network access to GitHub and any auth the marketplace needs. Trade-off: the cloud env must successfully reach the marketplace on every cold start.

**Option 3 — Bake into a custom image.** If you control the cloud image (Codespaces devcontainer, custom AMI, custom Hetzner template), install the plugin once at image-build time. Trade-off: image rebuilds needed for plugin updates.

### Where is the boundary between scopes?

- **User-level plugins** belong to the *operator*. They reflect personal workflow preferences. They don't follow the repo and don't follow teammates.
- **Repo-vendored plugins** belong to the *project*. They guarantee that every contributor (and every CI runner) uses the same workflow tooling. Use this when the workflow is part of how the project is meant to be built.
- **Repo-vendored agent/prompt overrides** at `.claude/ralph/{agents,prompts}/` are a *third, finer-grained* scope: the plugin itself can be user-level OR repo-vendored, and either way these overrides tune it for *this specific project*. That's how `theomedis-physio/.claude/ralph/agents/quality.md` could specialize the bundled quality agent for that codebase without forking the whole plugin.

A practical pattern:
- Solo / personal projects → user-level install + per-project overrides under `.claude/ralph/`.
- Team / cloud / CI → vendor the whole plugin into `.claude/plugins/ralph/` in each project that uses it. No drift, no install step, no marketplace dependency at runtime.

### Cloud runtime checklist

For any cloud env where ralph will run end-to-end:

- `git` ≥ 2.40 (for worktrees in wave mode)
- `bun` (or the project's chosen runtime) for lean validation
- `gh` CLI authenticated via `GITHUB_TOKEN` (for `/ralph pr`)
- Writable filesystem with enough space for `.ralph/worktrees/` if using wave mode
- `docs/plans/.scratch/` checked into the repo OR persisted across sessions — otherwise session manifests vanish on container restart and resume across cold starts won't work
- Playwright + browser binaries **only** in the env where you'll run `/ralph e2e` — the main loop never needs them

### What's better here than ralphex was

Ralphex required Docker-in-Docker (or nested containers) for its execution model. Many cloud platforms either forbid that or make it slow. `ralph` runs on a plain runtime — if there's `git` and `bun`, it works. Cloud deployment is "clone the repo" instead of "build and ship a container image."

## Status

v0.3.0 — capability-gated in-loop E2E added to `execute`: a hardened Step 1 environment probe (`exec_mode` / `run_prefix` / deps auto-install + verify / `e2e` capability) drives mandatory-when-available E2E — per-task dev-mode (single mode) + a post-review prod gate — with no mode menu; lean-only when E2E is unrunnable. Per-worktree-container **wave** E2E is the scoped follow-up. Each subcommand is self-contained and independently testable on a small change. Order of validation against a real repo: `pr` (smallest surface) → `brainstorm` → `review` → `execute` single mode (probe on a host-native repo, then a Docker repo, then an E2E-less repo) → `plan` single mode → `execute` wave mode → `plan` parallel mode → `e2e`.
