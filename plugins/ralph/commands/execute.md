---
description: Ralph execute — native ralph-loop. Auto-detects single-plan vs wave mode.
argument-hint: '[resume]'
---

# /ralph execute

Runs the native ralph-loop. **No Docker, no ralphex CLI.** All execution is via the Agent tool from this session.

## Step 0 — Mode detection

Look for an execution manifest at `docs/plans/*-execution.md`:
- **Manifest present** → wave mode (Step W*)
- **No manifest, single plan in `docs/plans/`** (unfinished — has `[ ]` boxes) → single mode (Step S*)
- **No manifest, no unfinished plan** → standalone fallback. Scan `docs/plans/` and `docs/plans/completed/`:
  - **If any plan has `[ ]` boxes** (incomplete) → offer to resume those plans (list them via AskUserQuestion). This includes plans that finished tasks but never went through the review loop — those count as incomplete.
  - **No incomplete plans, but completed ones exist** → ask:
    - "Re-review a completed plan" — runs S2 (review loop) only against the diff that the completed plan introduced (use `git log --grep '<plan-stem>'` to identify the range)
    - "Run `/ralph plan` first" (Recommended)
    - "Cancel"
  - **Nothing at all** → tell the user there is nothing to execute and suggest `/ralph plan` or `/ralph brainstorm`.

Never "re-run" a completed plan — completed means tasks are done and committed. The only valid follow-up actions are *resume the incomplete one* or *review the completed one again*.
- **`resume` argument** → read manifest's `Current State` and pick up where it stopped

If multiple manifests exist with non-`completed` state, ask the user which to execute via AskUserQuestion.

## Session manifest

Create per dispatcher spec (`commands/ralph.md` → "Session manifests"). `kind: execute`. `artifact:` points at the plan file (single mode) or the execution manifest (wave mode). `parent:` points at any preceding plan-session manifest if found.

For execute, the durable resume state is the plan file's checkbox state and (in wave mode) the execution manifest's `Current State`. The session manifest mirrors them for cross-session discoverability — checkpoint after each task completes, each wave transitions, and each review iteration.

## Step 1 — Pre-flight (both modes)

- `git status` clean (warn if not)
- `git branch --show-current` — not main/master
- If any plan has a `### BEFORE LAUNCH (host)` section: verify `package.json` + `bun.lock` already include the listed packages (`bun pm ls | grep <pkg>`). If missing, STOP and ask the user to install on the host before re-running.

No image build check — there is no image.

---

## SINGLE MODE (S)

### S1 — Task loop

Outer safety cap: **50 iterations** of this loop (matches ralphex `max_iterations` and cc-thingz). Reaching it means the plan is too large or something is stuck — surface to user.

For each unchecked `[ ]` task in the plan, in order:

1. Re-read the plan file (subagent modifies it each iteration).
2. Find the first task with `[ ]` checkboxes.
3. Dispatch an Agent (general-purpose, bypassPermissions) with:
   - The full plan file as context
   - The single task description as the target
   - `prompts/task.md` (override chain) as the contract — contract gives the Agent 1 dispatch with internal iteration freedom
   - The project's CLAUDE.md
4. Wait for completion. Re-read the plan. Check whether the task's `[ ]` boxes are now `[x]`.
5. On boxes checked + commit present → advance.
6. On boxes still unchecked OR `TASK_FAILED` signal: **one retry** with a fresh subagent for the same task (matches ralphex `task_retry_count=1`, cc-thingz `task_retries=1`).
7. If retry also fails: surface via AskUserQuestion:
   - "Edit plan and retry" — user revises; restart with fresh 2-attempt budget
   - "Skip task and continue" — mark `[~]` with `<!-- SKIPPED: <reason> -->` in the plan
   - "Abort" — stop the run

**Per-task budget:** 2 dispatches (1 + 1 retry). No more without user intervention.

**Orchestrator discipline (from cc-thingz):** you are the orchestrator. Never read code, debug, or fix issues yourself. If a subagent leaves problems, retry with a fresh subagent and pass the error details in the prompt.

### S2 — Review loop (after all tasks done)

Read `prompts/review.md` (override chain) and execute it as a playbook from THIS session. The playbook drives a unified loop:

- Iteration 1: comprehensive 5-agent fan-out
- Iterations 2–5: critical-only (quality + implementation)
- After each iteration: one fixer subagent with the full findings list
- Exit: all clean | HEAD unchanged after fixer | iteration cap (5)

The playbook is read by this session — subagents do NOT have the Agent tool, so fan-out must be initiated here.

### S3 — Finalize

- Final lean validation (`lint && typecheck && test:unit`)
- Ensure all `[ ]` boxes are checked
- Move the plan to `docs/plans/completed/`
- Commit the move

### S4 — Handoff

If `RALPH_AUTO_PR` is set:
- If user said `"hardened"` or `"with review"` → chain into `/ralph review`
- Otherwise → chain into `/ralph pr` (lean mode)

Otherwise, ask via AskUserQuestion:
- header: "Next"
- question: "Execute complete. What next?"
- options:
  - "Visual review (`/ralph review`)" (Recommended) — accumulate or fix-now Q&A walkthrough
  - "Create PR now (`/ralph pr`)" — lean mode, no review, no E2E
  - "Stop" — finish here, decide later

---

## WAVE MODE (W)

### W1 — Launch current wave

For each plan in the current wave (read from manifest):

1. Create a host-side worktree:
   ```bash
   git worktree add .ralph/worktrees/<plan-stem> -b ralph-<plan-stem>
   ```
2. Copy the plan file into the worktree (worktrees branch from HEAD-before-plan-was-committed):
   ```bash
   cp docs/plans/<plan-file>.md .ralph/worktrees/<plan-stem>/docs/plans/
   ```
3. Spawn a **background Agent** per plan, instructed to run **S1 only** (tasks + lean validation + commits) on its plan from inside its worktree. NO review fan-out on per-wave plans — matches ralphex `--tasks-only`. Record task IDs in the manifest.

Constraint: parallel Agents must come from THIS session (top-level). Subagents cannot spawn subagents. The ralph-loop inside each background Agent dispatches per-task subagents within its own scope — that's one level of nesting, allowed.

Update the manifest's Execution Log:
```markdown
### Wave N — started <ISO timestamp>
| Plan | Branch | Status | Task ID |
|------|--------|--------|---------|
| <plan-stem> | ralph-<plan-stem> | running | <id> |
```

### W2 — Monitor

On "check ralph" / "status": read each plan's checkbox progress + last lines of any progress channel. Flag stalls and repeated failures.

### W3 — Wave transition

When all background Agents in the wave finish:
- On any failure: ask user (fix and retry / skip / abort)
- On all green: merge wave branches into the parent branch
  ```bash
  git merge ralph-<plan-stem-1> ralph-<plan-stem-2> ...
  ```
- Advance to next wave (back to W1)

### W4 — Merge wave

The merge plan runs as a full single-mode loop in its own worktree: **S1 (tasks) + S2 (review loop) + S3 (finalize)**. The git-diff-driven review naturally covers the consolidated change surface — reviewing pre-merge per-branch would produce false positives about missing wiring and waste 5×N agent runs.

This is why per-wave plans run tasks-only and the merge plan runs the full pipeline — same split as ralphex `--tasks-only` + merge-with-review.

### W5 — Cleanup + handoff

- Set manifest `Current State: completed`
- `git worktree prune` and remove `.ralph/worktrees/*` directories
- Move the manifest to `docs/plans/completed/`
- Handoff per S4 (auto-PR / ask)

## Pause / Resume

- "pause" → stop all background Agents (record task IDs as `paused` in manifest), commit the manifest, exit.
- "resume" / `/ralph execute resume` → read manifest, recreate any removed worktrees from their branches, restart paused Agents.
