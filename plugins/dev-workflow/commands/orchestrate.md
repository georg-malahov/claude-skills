---
description: Plan or execute multi-wave parallel ralphex orchestration
argument-hint: '"plan <description>" or "execute" or "resume"'
---

# Orchestrate — Parallel Plan Generation and Execution

Single entry point with two subcommands:

- `/orchestrate plan <description>` — grill → decompose → emit per-wave plans + merge plan + execution manifest
- `/orchestrate execute` — pre-flight, launch ralphex with `--tasks-only`, monitor, run merge plan, hand off to `/create-pr`
- `/orchestrate resume` — pick up a paused orchestration (see Resume section)

The two subcommands are deliberately split: planning is interactive and slow; execution is mostly autonomous and benefits from a clean pre-flight gate.

**Parse `$ARGUMENTS`:** first token decides the branch.
- `plan` or `plan <rest>` → Plan flow
- `execute` → Execute flow
- `resume` → Resume flow
- empty or anything else → ask user which subcommand they want via AskUserQuestion

---

## PLAN FLOW (`/orchestrate plan`)

### Step P0: Parse Intent and Gather Context

1. **Parse the user's description** to understand the high-level goal.

2. **Launch Explore agent** to gather relevant codebase context:
   - Existing models, routes, components related to the goal
   - Patterns and conventions already established
   - Files and modules that will be affected
   - Current state of any related work (check `docs/plans/` for related plans)

3. **Synthesize findings** into a context summary. Present it to the user before proceeding.

### Step P1: Grill — Deep Context Gathering

Interview the user relentlessly about every aspect of the work until reaching shared understanding. This is the most critical phase — the quality of plans depends entirely on context gathered here.

**How to grill:**
- Ask questions **one at a time** using AskUserQuestion
- For each question, provide your **recommended answer** as the first option
- Walk down each branch of the decision tree, resolving dependencies one-by-one
- If a question can be answered by exploring the codebase, **explore instead of asking**
- Challenge assumptions — ask "why" and "what if"
- Focus on questions that reveal parallelism opportunities:
  - What are the distinct entities, services, and UI surfaces involved?
  - Which parts share data or state? Which are independent?
  - Are there shared UI containers (layouts, navigation) that multiple features plug into?
  - What is the minimum viable integration point between parallel tracks?
  - Are there sequence constraints (e.g., schema must exist before UI)?

**Keep grilling until you can answer:**
1. What are all the distinct work streams?
2. For each pair of work streams: does one depend on the other, or are they independent?
3. What shared resources (schema, layouts, navigation, services) must exist before parallel work begins?
4. What integration points need a merge step afterward?

When you have enough context, summarize your understanding and ask the user to confirm before proceeding to decomposition.

### Step P2: Decompose — Build the Dependency Graph

Analyze the work streams identified in Step P1 and organize them into waves:

1. **Identify the foundation** — shared work that everything else depends on (schema changes, navigation shell, shared services). This is always Wave 1 and runs as a single plan if it can't be parallelized.

2. **Identify independent tracks** — work streams that don't depend on each other after the foundation is in place. These form parallel plans in Wave 2.

3. **Identify sequential dependencies** — work that must follow a specific track. These go into later waves.

4. **Always add a final merge wave** — see Step P4 for what it contains.

**Present the DAG to the user:**

```
Wave 1 (sequential): [foundation plan]
Wave 2 (parallel):   [plan-a] | [plan-b] | [plan-c]
Wave 3 (parallel):   [plan-d] | [plan-e]  (depends on wave 2)
Wave N (merge):       [merge-plan]
```

Use AskUserQuestion to confirm the decomposition before generating plans.

### Step P2.5: Validate — Plan Size, Parallelism, Mocks

After the user confirms the initial decomposition, perform a critical validation pass:

**Size and manageability check** — for each plan in the DAG:
- **Ideal**: 3-6 tasks per plan, each completable in a single ralphex iteration
- **Too large**: 7+ tasks or tasks combining multiple concerns → split
- **Too small**: 1-2 tasks → merge with related plans

**Parallelism maximization with mocks** — challenge every dependency between plans. Ask: "Can this dependency be eliminated with a mock or interface contract?"

Since all plans are well-defined with known inputs/outputs, parallel plans can use **mocks and stubs** for components built by sibling plans. The merge plan replaces mocks with real implementations.

Examples:
- A plan building a tab component doesn't need the workspace shell — it can render standalone or use a mock wrapper
- A plan building a service doesn't need the UI — test it with unit tests against the real DB
- A plan building UI doesn't need the real service — it can mock API responses matching the planned contract

When a plan uses mocks for parallel siblings, document them explicitly in the plan:
```markdown
### Mocks (removed during merge)
- `<path-to-mock-file>` — what it stubs
- Mock API response for `<endpoint>` — what shape it returns
```

The merge plan MUST include a task to:
1. Remove all mock files
2. Replace mock imports with real implementations
3. Verify no mock references remain (`grep -r "mock" src/`)

Present the validated plan structure to the user with task counts and mock strategy. Use AskUserQuestion to confirm before generating plans.

### Step P3: Generate Per-Wave Plans — LEAN

For each work stream, write a plan file in `docs/plans/YYYY-MM-DD-<name>.md`.

**Use parallel Agent instances** to generate independent plans simultaneously. Each agent receives:
- The full context summary from Step P1
- The specific scope for its work stream
- Awareness of what other parallel plans are doing (to avoid conflicts)
- Dependencies: which plans must complete before this one starts

**LEAN PLANS — critical change**: per-task ralphex runs in Execute Flow will use `--tasks-only`. That means per-task plans **do not include** preview deploys, E2E runs, or review iterations. Each plan's terminal task is a lightweight validation:

> `bun run lint && bun run typecheck && bun run test:unit` (or the project's equivalent — see user-level CLAUDE.md "Run validation")

E2E + review + preview/screenshot sanity checks are **consolidated into the merge plan** (Step P4).

**Each lean plan follows this format:**

```markdown
# [Plan Title]

## Overview
[What this plan delivers and why]

## Context
[Full context from Step P1, scoped to this work stream]
[Dependencies: list which plans must complete before this one]
[Parallel awareness: what other plans are running alongside, what they touch]
[Mocks used (if any): see Step P2.5]

## Development Approach
- Testing approach: [TDD / Regular]
- CRITICAL: every task MUST include tests
- CRITICAL: all tests must pass before starting next task
- CRITICAL: update this plan file when scope changes
- CRITICAL: this plan runs with ralphex --tasks-only. No preview, no E2E, no review.
  Those run in the merge plan.

## Testing Strategy
- Unit tests: required for every task
- E2E tests: deferred to merge plan
- Validation per task: lint + typecheck + unit (project's "run validation" subset)

## Implementation Steps

### Task 1: [specific name]
- [ ] [specific action with file reference]
- [ ] write unit tests
- [ ] run lint + typecheck + unit — must pass before next task

### Task N: Verify
- [ ] verify all requirements implemented
- [ ] run lint + typecheck + unit (one final time)
```

### Step P4: Generate Merge Plan — HEAVY

Generate the merge plan at `docs/plans/YYYY-MM-DD-<feature>-merge.md`. This is where **all the deferred verification** happens.

The merge plan's Context section **enumerates every per-wave plan** by file path + branch name + intended goal. This is the manifest cross-check surface.

Merge plan tasks:

```markdown
### Task 1: Manifest cross-check
- [ ] Read execution-manifest.md and list every plan + branch
- [ ] For each manifest entry, confirm commits appear in `git log <default-branch>..HEAD`
- [ ] Flag any plan whose changes are missing from the merged history

### Task 2: Remove mocks (if any)
- [ ] Delete files listed under "Mocks (removed during merge)" in each per-wave plan
- [ ] Replace mock imports with real implementations
- [ ] Verify: `grep -r "mock" src/` returns no orphan references

### Task 3: Wire components together
- [ ] Plug tab components into workspace shell, connect pages to navigation, etc.
- [ ] Specific wiring steps depend on the feature — list them per plan

### Task 4: Full validation
- [ ] Run the project's full validation suite (see user-level CLAUDE.md "Run validation")
  - In ralphex/container: `bun run lint && bun run typecheck && bun run test:unit && bun run test:e2e`
  - From host: prefix with `bun run dx bun run ...`
- [ ] E2E: rerun ONLY failing suites on iteration; don't re-run the full suite each time
- [ ] All must pass before continuing

### Task 5: Preview / screenshot sanity check
- [ ] Invoke `/preview-check` with the affected routes
- [ ] Verify mobile + desktop viewports render correctly
- [ ] Attach the resulting markdown report's screenshots to the PR description (deferred to /create-pr)

### Task 6: Update documentation
- [ ] Regenerate architecture diagrams if relevant (`/generate-docs` or equivalent)
- [ ] Update README/CHANGELOG if user-facing
```

The merge plan runs ralphex with full review iterations (NOT `--tasks-only`) — the existing ralphex review pass is already git-diff-driven across the whole branch, so it naturally covers the consolidated change surface.

### Step P5: Write Execution Manifest

Write the execution manifest at `docs/plans/YYYY-MM-DD-<feature>-execution.md`.

```markdown
# Execution Manifest: [Feature Name]

## Overview
[One paragraph summary of the full feature]

## Context Gathered
[Key decisions and context from the grill phase]

## Dependency Graph

Wave 1 (foundation): docs/plans/YYYY-MM-DD-<name>.md
Wave 2 (parallel):
  - docs/plans/YYYY-MM-DD-<name-a>.md
  - docs/plans/YYYY-MM-DD-<name-b>.md
Wave N (merge): docs/plans/YYYY-MM-DD-<feature>-merge.md

## Execution Log

_Updated during execution. This section is the persistent state that enables pause/resume._

### Current State: not_started

### Wave 1 — not_started
| Plan | Branch | Status | Notes |
|------|--------|--------|-------|
| plan-name | worktree-plan-name | pending | |

### Wave 2 — not_started
| Plan | Branch | Status | Notes |
|------|--------|--------|-------|
```

After generating all plans + the manifest, present a summary of what was created and confirm with the user. Then suggest `/orchestrate execute` to launch.

---

## EXECUTE FLOW (`/orchestrate execute`)

### Step E0: Pre-flight Check (MANDATORY)

Run this BEFORE launching any wave. If anything fails, summarize and ask the user to fix before continuing — do not proceed automatically.

```bash
# 1. Worktree state
git worktree list
git status
git branch --show-current

# 2. Uncommitted changes — must be clean (warn if not)
test -z "$(git status --porcelain)" || echo "WARN: uncommitted changes"

# 3. Ralphex CLI present (host-side or container-wrapper)
which ralphex || test -x bin/ralphex-dk || echo "WARN: no ralphex / ralphex-dk binary"

# 4. Docker image present (read image name from project config — do NOT hardcode)
#    Look at scripts/up.ts, .ralphex/config, or the bin/ralphex-dk wrapper.
#    Then: docker image inspect <name> >/dev/null || echo "WARN: image missing"
```

Additionally:
- Look at `docs/plans/*-execution.md` to identify which orchestration is being executed
- Confirm the manifest's `Current State` is `not_started` (otherwise route to RESUME)
- Confirm each per-wave plan file referenced in the manifest exists

**Summarize the pre-flight state** to the user. Use AskUserQuestion to confirm before launching.

If image is missing, suggest `bun run image:build` (or the project's image-build command).

### Step E1: Launch Current Wave

**Isolation: create worktrees on the HOST, run ralphex-dk from each worktree.**

Git worktrees use absolute paths. They must be created on the host — never inside Docker (container-internal paths break after the container stops). `ralphex-dk` automatically mounts `$(pwd)` as `/workspace` and the main `.git` directory at its host path, so git operations inside the container resolve correctly.

For each plan in the current wave:

1. Create a host-side worktree and branch:
```bash
git worktree add .ralphex/worktrees/<plan-stem> -b worktree-<plan-stem>
```

2. **Copy plan files into the worktree.** Plan files are written to the parent worktree's `docs/plans/` during Plan flow, but worktrees branch from the parent's HEAD at the time of creation — which is BEFORE the plan files were committed. Without this copy, ralphex will fail with "plan file not found":
```bash
cp docs/plans/<plan-file>.md .ralphex/worktrees/<plan-stem>/docs/plans/<plan-file>.md
```

3. Run `bin/ralphex-dk` from the worktree directory with `--tasks-only`:
```bash
cd .ralphex/worktrees/<plan-stem> && \
  bin/ralphex-dk --tasks-only --max-iterations 50 --wait 1h docs/plans/<plan-file>.md
```

- `--tasks-only` is the key change: skips per-task preview/review iterations. Per-task plans now only run lean validation (lint + typecheck + unit). E2E + review + preview move to the merge plan.
- `--wait 1h` is critical for parallel runs: when a rate limit is hit, ralphex waits and retries instead of exiting. Also configure `wait_on_limit = 1h` in `.ralphex/config`.

Each worktree has the full repo structure including `bin/ralphex-dk`. Running from the worktree directory makes `ralphex-dk` mount that worktree (not the main repo) as `/workspace`. Each container gets its own isolated file tree — no shared mount conflicts, no `--worktree` flag needed.

**Branch strategy:** All work happens on local branches. Pushes to GitHub are backup only — the merge plan works with local branches via `git merge`, never fetches from remote to get parallel-track results.

Run each via Bash tool with `run_in_background: true`. Record task IDs and branch names.

**Update the execution manifest** after launching each wave (this is the persistent state file):

```markdown
## Execution Log

### Wave 1 — started 2026-MM-DDTHH:MM
| Plan | Branch | Status | PID |
|------|--------|--------|-----|
| <plan-stem> | worktree-<plan-stem> | running | <pid> |
```

Update statuses as plans complete: `running` → `completed` or `failed`. This state survives session interruptions — a new session can read it and resume.

Report launch status:

```
Launched wave N:
  [plan-a] — task_id: X, progress: .ralphex/progress/progress-plan-a.txt
  [plan-b] — task_id: Y, progress: .ralphex/progress/progress-plan-b.txt

Monitoring progress. Ask "check orchestrate" for status.
Commands: "pause" to stop all processes, "resume" to continue.
```

### Step E2: Monitor Progress

When the user asks "check orchestrate", "status", or similar:

1. For each running plan, read last 30 lines of its progress file
2. Check TaskOutput with `block: false` for each task ID
3. Report status per plan:
   - Current task number and description
   - Phase (task execution / lean validation)
   - Any warnings or failures detected

**Proactive intervention signals** (flag these to user):
- Progress file shows repeated failures on same task
- `TASK_FAILED` appears in progress
- No progress for extended period (same content on consecutive checks)
- Plan appears to be going off-track (implementation doesn't match intent)

**If intervention needed:**
1. Suggest killing the process and editing the plan
2. On user approval: kill the process, edit the plan file with corrective instructions
3. Relaunch ralphex on the same plan — it picks up from the first unchecked task

### Step E3: Wave Transition

When all plans in a wave complete:

1. Report results for each plan
2. If any failed: ask user whether to fix and retry, skip, or abort
3. If all succeeded: **merge completed wave branches into the parent branch** so the next wave starts from an up-to-date base:
```bash
git merge worktree-<plan-stem-1> worktree-<plan-stem-2> ...
```

   Child worktrees branch from the parent's HEAD. Without merging wave results back, the next wave's worktrees would miss the previous wave's changes.

   For single-plan waves: simple `git merge worktree-<plan-stem>`. For multi-plan waves: octopus merge or sequential merges. Resolve conflicts if any.

4. Announce next wave and ask to proceed
5. Launch next wave (return to E1)

### Step E4: Merge Wave

The merge plan is generated during Plan flow (Step P4). It gets its own host-side worktree and runs ralphex **WITHOUT** `--tasks-only` — the full review pass is desired here because:
- The git-diff-driven review naturally covers the whole branch's changes
- E2E, preview, manifest cross-check are all explicit tasks in the merge plan body

```bash
git worktree add .ralphex/worktrees/<merge-plan-stem> -b worktree-<merge-plan-stem>
cp docs/plans/<merge-plan>.md .ralphex/worktrees/<merge-plan-stem>/docs/plans/
cd .ralphex/worktrees/<merge-plan-stem> && \
  bin/ralphex-dk --max-iterations 50 --wait 1h docs/plans/<merge-plan>.md
```

Ralphex runs its review and finalize phases on the merge plan as usual.

When the merge plan completes, **remind the user to invoke `/create-pr`**. Do NOT auto-run it — PR creation is a separate explicit step that gates on green validation independently.

### Step E5: Cleanup

After orchestration is complete (merge plan done, user has invoked `/create-pr`):

1. **Update the execution manifest**: set `Current State: completed`.

2. **Ensure completed plans have all checkboxes checked.** The parent worktree's `docs/plans/` directory contains the **original plan files** written during Plan flow — these have unchecked `[ ]` boxes. Ralphex updates checkboxes and moves plans to `docs/plans/completed/` inside each **child worktree**. After merging child branches, the correct checked versions are already on the merged branch in `docs/plans/completed/`.

   **Do NOT manually move plan files from the parent's `docs/plans/` to `completed/`** — this overwrites the checked versions with stale unchecked originals.

   Instead:
   - Verify `docs/plans/completed/` contains the checked plans: `grep -c '\- \[ \]' docs/plans/completed/2026-*` — should be 0 for each file
   - If any plan is missing from `completed/`, copy it from the child worktree
   - Delete the stale untracked originals from the parent's `docs/plans/`
   - Move the execution manifest to `completed/`: `mv docs/plans/*-execution.md docs/plans/completed/`

3. **Prune stale worktree references:** `git worktree prune`

4. **Remove local worktree directories**: `git worktree remove .ralphex/worktrees/<name>` for each intermediate worktree.

5. **Remote branch cleanup** is handled by `/create-pr` Step 5.

---

## RESUME FLOW (`/orchestrate resume`)

Triggered explicitly or when the user says "resume", "continue orchestration", or starts a new session and asks to continue.

1. **Find the execution manifest** — scan `docs/plans/**/execution-manifest.md` for the active orchestration. Look for `Current State:` that is NOT `not_started` or `completed`.

2. **Read the execution log** to determine current state — which wave is active, which plans are `completed`, `paused`, or `failed`.

3. **For each incomplete plan**, check its plan file for task checkboxes — count `[x]` (done) vs `[ ]` (pending). Ralphex will resume from the first unchecked task automatically.

4. **Verify worktrees still exist:**
```bash
git worktree list
```
   If a worktree was removed, recreate it from the plan's branch:
```bash
git worktree add .ralphex/worktrees/<plan-stem> worktree-<plan-stem>
```
   The branch still exists in git — only the working directory needs recreation.

5. **Report current state to the user:**
```
Resuming orchestration at Wave N:
  plan-a:    completed (4/4 tasks)
  plan-b:    paused at task 3/6
  ...

Ready to relaunch <N> paused plans. Proceed?
```

6. **On user confirmation**, relaunch paused plans with `--tasks-only` (per-wave) or without (merge plan):
```bash
cd .ralphex/worktrees/<plan-stem> && \
  bin/ralphex-dk --tasks-only --max-iterations 50 --wait 1h docs/plans/<plan-file>.md
```

7. **Update execution manifest** — set relaunched plans back to `running`.

---

## PAUSE

When the user says "pause", "stop", or similar:

1. **Kill all running ralphex processes:**
```bash
docker ps --filter "name=ralphex" --format "{{.Names}}" | xargs -r docker stop
```
   Ralphex saves progress via task checkboxes in the plan file after each completed task, so killing mid-run loses at most the currently executing task (it will be retried on resume).

2. **Update the execution manifest** — set running plans to `paused`.

3. **Commit the execution manifest** so state is preserved even if the worktree is disrupted:
```bash
git add docs/plans/**/execution-manifest.md && git commit -m "orchestrate: pause at wave N"
```

4. Confirm to the user: "Orchestration paused at Wave N. Resume anytime with `/orchestrate resume`."

---

## Key Principles

- **One question at a time** during the grill phase
- **Recommend an answer** for every question — have an opinion
- **Explore codebase** instead of asking when the answer is in the code
- **Maximize parallelism** — only mark as sequential what truly must be sequential
- **Use mocks to eliminate dependencies** — parallel plans can mock sibling plan outputs; the merge plan removes mocks and wires real implementations
- **Lean per-wave plans, heavy merge plan** — `--tasks-only` for per-wave, full review + E2E + preview for merge
- **Validate plan size before generating** — each plan should have 3-6 focused tasks; split large plans, merge tiny ones
- **Context is king** — every plan gets the full context so ralphex subprocesses make informed decisions
- **The merge plan is mandatory** — parallel work always needs integration validation, mock removal, component wiring, and the deferred verification (E2E, preview)
- **Rate limits are expected** — always use `--wait 1h` for parallel runs
- **Intervention over waiting** — proactively flag issues rather than waiting for TASK_FAILED
- **Pre-flight is mandatory** — Execute flow always runs Step E0 before launching
- **PR creation is separate** — `/orchestrate execute` ends by reminding the user to run `/create-pr`, never auto-runs it
